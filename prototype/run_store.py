"""Private, atomic single-process run and review storage for the local application.

Only the application publishes reports. Imported browser JSON never enters this store.
The integrity key detects corrupted/edited records; it is not a signature against the
local account owner, who can access the key. Linux/macOS runtime; Windows uses Docker.
"""
import copy
import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .contracts import Requirements
from . import requirements_review as requirements_review
from .pipeline import refresh_derived
from .privacy_core import REFERENCE, RESERVED
from .review_policy import Decision, closing_decision, current_versions

ACTIVE = {'queued', 'running'}
STATES = ACTIVE | {'complete', 'partial', 'failed', 'cancelled', 'interrupted'}
ID = re.compile(r'[0-9a-f]{32}\Z')
KEY = re.compile(r'[a-zA-Z0-9_.:-]{1,128}\Z')
MAX_RECORD = 32_000_000
MAX_VIEW = 15_000_000  # HTTP envelope limit is 16 MB, including review wrapper.


class StoreError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _digest(value):
    return hashlib.sha256(_json(value)).hexdigest()


def _request_digest(request):
    return _digest({k:v for k,v in request.items() if k != 'total'})


class RunStore:
    def __init__(self, root):
        self.root = Path(root)
        if self.root.is_symlink():
            raise StoreError('unsafe_path')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        self._mutex = threading.RLock()
        self._rootfd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self._lockfd = None
        self._closed = False
        try:
            self._lockfd = os.open('.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=self._rootfd)
            try:
                fcntl.flock(self._lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise StoreError('store_in_use') from None
            try:
                fd = os.open('.integrity-key', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=self._rootfd)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd, 'wb') as handle:
                    handle.write(secrets.token_bytes(32))
                    handle.flush()
                    os.fsync(handle.fileno())
            fd = os.open('.integrity-key', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self._rootfd)
            with os.fdopen(fd, 'rb') as handle:
                self._key = handle.read(33)
            if len(self._key) != 32:
                raise StoreError('store_corrupt')
            for name in self._names():
                if re.fullmatch(r'\.(creating|deleting)-[0-9a-f]{32}', name):
                    self._remove_directory(name)
            for rid in self._ids():
                record = self._read(rid)
                if record['state'] in ACTIVE:
                    record.update(state='interrupted', stage='interrupted', error='interrupted', updated_at=_now())
                    self._write(record)
        except BaseException:
            self.close()
            raise

    def close(self):
        with self._mutex:
            if self._closed:
                return
            self._closed = True
            if self._lockfd is not None:
                os.close(self._lockfd)
            os.close(self._rootfd)

    def _names(self):
        if self._closed:
            raise StoreError('store_closed')
        # A duplicated directory fd shares its read offset on Linux. Open a new
        # file description each time so a just-created run is never skipped.
        fd = os.open('.', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self._rootfd)
        try:
            return os.listdir(fd)
        finally:
            os.close(fd)

    def _ids(self):
        return sorted(n for n in self._names() if ID.fullmatch(n))

    def _remove_directory(self, name):
        if not re.fullmatch(r'\.(creating|deleting)-[0-9a-f]{32}', name):
            raise StoreError('unsafe_path')
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self._rootfd)
        try:
            for entry in os.listdir(fd):
                os.unlink(entry, dir_fd=fd)  # never follows a symlink or descends
        finally:
            os.close(fd)
        os.rmdir(name, dir_fd=self._rootfd)
        os.fsync(self._rootfd)

    def _dir(self, rid):
        if not isinstance(rid, str) or not ID.fullmatch(rid):
            raise StoreError('not_found')
        try:
            return os.open(rid, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self._rootfd)
        except FileNotFoundError:
            raise StoreError('not_found') from None
        except OSError:
            raise StoreError('unsafe_path') from None

    def _read(self, rid):
        directory = self._dir(rid)
        try:
            try:
                fd = os.open('record.json', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            except OSError:
                raise StoreError('unsafe_path') from None
            with os.fdopen(fd, 'rb') as handle:
                raw = handle.read(MAX_RECORD + 1)
            if len(raw) > MAX_RECORD:
                raise StoreError('store_corrupt')
            try:
                envelope = json.loads(raw)
                record, signature = envelope['record'], envelope['hmac']
                expected = hmac.new(self._key, _json(record), hashlib.sha256).hexdigest()
                if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
                    raise ValueError()
                if record['run_id'] != rid or record['store_version'] != '0.1' or record['state'] not in STATES:
                    raise ValueError()
                return record
            except (ValueError, TypeError, KeyError, UnicodeError):
                raise StoreError('store_corrupt') from None
        finally:
            os.close(directory)

    def _write(self, record, *, directory=None):
        raw = _json(record)
        envelope = _json({'record':record, 'hmac':hmac.new(self._key, raw, hashlib.sha256).hexdigest()})
        if len(envelope) > MAX_RECORD:
            raise StoreError('record_too_large')
        own_directory = directory is None
        if own_directory:
            directory = self._dir(record['run_id'])
        name = '.tmp-' + uuid4().hex
        try:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            with os.fdopen(fd, 'wb') as handle:
                handle.write(envelope)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, 'record.json', src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            try:
                os.unlink(name, dir_fd=directory)
            except FileNotFoundError:
                pass
            if own_directory:
                os.close(directory)

    @staticmethod
    def _summary(record):
        fields = ('run_id','mode','scenario','created_at','updated_at','state','stage','processed','total','error')
        return {**{k:record[k] for k in fields}, 'report_available':record['report'] is not None,
                'revision':record['revision'] or None}

    def get(self, rid):
        with self._mutex:
            return self._summary(self._read(rid))

    def list(self):
        with self._mutex:
            return sorted((self._summary(self._read(rid)) for rid in self._ids()),
                          key=lambda r:r['created_at'], reverse=True)

    def create(self, request, idempotency_key):
        if not isinstance(idempotency_key, str) or not KEY.fullmatch(idempotency_key):
            raise StoreError('invalid_idempotency_key')
        fingerprint = _request_digest(request)
        with self._mutex:
            records = [self._read(rid) for rid in self._ids()]
            for r in records:
                if r['idempotency_key'] == idempotency_key:
                    if r['request_digest'] != fingerprint:
                        raise StoreError('idempotency_conflict')
                    return self._summary(r), False
            if any(r['state'] in ACTIVE for r in records):
                raise StoreError('busy')
            if len(records) >= 200:
                raise StoreError('store_full')
            rid, now = uuid4().hex, _now()
            record = dict(store_version='0.1', run_id=rid, mode=request['mode'], scenario=request.get('scenario'),
                          created_at=now, updated_at=now, state='queued', stage='queued', error=None,
                          processed=0, total=request.get('total', 3), revision=0, report=None, sources=None,
                          idempotency_key=idempotency_key, request_digest=fingerprint, decisions=[], review_requests={})
            staging = '.creating-' + rid
            os.mkdir(staging, 0o700, dir_fd=self._rootfd)
            directory = os.open(staging, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self._rootfd)
            try:
                self._write(record, directory=directory)
                os.rename(staging, rid, src_dir_fd=self._rootfd, dst_dir_fd=self._rootfd)
                os.fsync(self._rootfd)
            finally:
                os.close(directory)
                try:
                    self._remove_directory(staging)
                except FileNotFoundError:
                    pass
            return self._summary(record), True

    def lookup_request(self, request, idempotency_key):
        if not isinstance(idempotency_key, str) or not KEY.fullmatch(idempotency_key):
            raise StoreError('invalid_idempotency_key')
        with self._mutex:
            for rid in self._ids():
                record = self._read(rid)
                if record['idempotency_key'] == idempotency_key:
                    if record['request_digest'] != _request_digest(request):
                        raise StoreError('idempotency_conflict')
                    return self._summary(record)
        return None

    def start(self, rid):
        with self._mutex:
            record = self._read(rid)
            if record['state'] != 'queued':
                raise StoreError('invalid_transition')
            record.update(state='running', stage='starting', updated_at=_now())
            self._write(record)

    def progress(self, rid, event):
        with self._mutex:
            record = self._read(rid)
            if record['state'] not in ACTIVE:
                return
            # Never persist arbitrary callback payloads or source text in progress.
            stage = event.get('stage')
            if not isinstance(stage, str) or not re.fullmatch(r'[a-z_]{1,60}', stage):
                return
            record.update(stage=stage, updated_at=_now())
            if stage == 'job_finished' and isinstance(event.get('job_id'), str):
                completed = set(record.get('completed_job_ids', []))
                completed.add(event['job_id'])
                record['completed_job_ids'] = sorted(completed)
                record['processed'] = len(completed)
            self._write(record)

    @staticmethod
    def _validate_snapshot(report, sources):
        try:
            sha = lambda value:hashlib.sha256(value.encode()).hexdigest()
            if sha(sources['resume']) != report['safe_resume_sha256']:
                raise ValueError()
            expected = {j['job_id'] for j in report['ranking']['jobs']} | set(report['unprocessed_job_ids'])
            if set(sources['jobs']) != expected:
                raise ValueError()
            for job in report['ranking']['jobs']:
                text = sources['jobs'][job['job_id']]
                if sha(text) != job['safe_source_sha256']:
                    raise ValueError()
                Requirements.model_validate(job['requirements']).validate_source(text)
        except (ValueError, TypeError, AttributeError, KeyError):
            raise StoreError('snapshot_mismatch') from None

    @staticmethod
    def _validate_display_aliases(aliases, sources):
        if not isinstance(aliases, dict):
            raise StoreError('invalid_display_aliases')
        if aliases:
            references = {m.group() for text in (sources['resume'], *sources['jobs'].values())
                          for m in REFERENCE.finditer(text)}
            if any(ref not in references or not isinstance(value, str) or not value.strip()
                   or RESERVED in value.upper() for ref, value in aliases.items()):
                raise StoreError('invalid_display_aliases')
            if len(_json(aliases)) > MAX_VIEW:
                raise StoreError('record_too_large')

    def finish(self, rid, report, sources, *, display_aliases=None):
        self._validate_snapshot(report, sources)
        aliases = {} if display_aliases is None else display_aliases
        self._validate_display_aliases(aliases, sources)
        with self._mutex:
            record = self._read(rid)
            if record['state'] != 'running':
                raise StoreError('invalid_transition')
            report = copy.deepcopy(report)
            report['run_id'] = rid
            record.update(report=report, sources=copy.deepcopy(sources), revision=1,
                          state=('complete' if report['ranking']['complete'] else
                                 'partial' if report['ranking']['jobs'] else 'failed'),
                          stage='finished', processed=len(report['ranking']['jobs']), updated_at=_now())
            if aliases:
                record['display_aliases'] = aliases.copy()
            if report.get('errors'):
                terminal = next((e for e in report['errors'] if e['code'] != 'model_invalid'), report['errors'][0])
                record.update(error=terminal['code'], stage=terminal['stage'])
            if any(e['code'] == 'cancelled' for e in report.get('errors', [])):
                record.update(state='cancelled', error='cancelled')
            self._view(record)  # Reject a report the transport cannot serve before publication.
            self._write(record)

    def fail(self, rid, code):
        if not isinstance(code, str) or not re.fullmatch(r'[a-z_]{1,80}', code):
            code = 'internal_error'
        with self._mutex:
            record = self._read(rid)
            if record['state'] not in ACTIVE:
                return
            record.update(state='cancelled' if code == 'cancelled' else 'failed',
                          error=code, updated_at=_now())
            self._write(record)

    def _view(self, record):
        if record['report'] is None:
            raise StoreError('report_unavailable')
        report = copy.deepcopy(record['report'])
        report['run_id'] = record['run_id']
        self._validate_snapshot(report, record['sources'])
        refresh_derived(report, record['decisions'])
        queue = {i['id']:i for i in report['review_queue']['items']}
        for item in report['handoff']:
            valid = item['state'] not in {'invalid', 'stale'}
            item['allowed_actions'] = {iid:closing_decision(queue[iid]['reason_code'])
                                      for iid in item['open_items'] if valid and
                                      closing_decision(queue[iid]['reason_code']) in {'read_context','accept_condition'}}
            item['can_confirm_requirements'] = valid and not item['requirements_confirmed']
            item['can_mark_for_handoff'] = (valid and item['state'] != 'reviewed_for_handoff'
                                           and not item['blockers'] and not item['open_items'])
        report.update(run_id=record['run_id'], revision=record['revision'],
                      review_history=copy.deepcopy(record['decisions']))
        if len(_json(report)) > MAX_VIEW:
            raise StoreError('record_too_large')
        return report

    def report(self, rid):
        with self._mutex:
            return self._view(self._read(rid))

    def display_data(self, rid):
        with self._mutex:
            record = self._read(rid)
            if record['report'] is None:
                raise StoreError('report_unavailable')
            return {'run_id':rid, 'revision':record['revision'],
                    'aliases':record.get('display_aliases', {})}

    def review(self, rid, action):
        fields = {'expected_revision','job_id','action','item_id','idempotency_key'}
        if not isinstance(action, dict) or set(action) != fields or type(action.get('expected_revision')) is not int:
            raise StoreError('invalid_action')
        if not isinstance(action['job_id'], str) or not isinstance(action['action'], str):
            raise StoreError('invalid_action')
        key = action.get('idempotency_key')
        if not isinstance(key, str) or not KEY.fullmatch(key):
            raise StoreError('invalid_idempotency_key')
        fingerprint = _digest(action)
        with self._mutex:
            record = self._read(rid)
            previous = record['review_requests'].get(key)
            if previous is not None:
                if previous != fingerprint:
                    raise StoreError('idempotency_conflict')
                return {'run':self._summary(record), 'report':self._view(record)}
            if action['expected_revision'] != record['revision']:
                raise StoreError('stale_revision')
            if len(record['decisions']) >= 2000:
                raise StoreError('review_limit')
            report = self._view(record)
            handoff = next((h for h in report['handoff'] if h['job_id'] == action['job_id']), None)
            if handoff is None:
                raise StoreError('unknown_job')
            kind, item_id = action['action'], action['item_id']
            allowed = ((kind == 'confirm_requirements' and item_id is None and handoff['can_confirm_requirements'])
                       or (kind == 'mark_for_handoff' and item_id is None and handoff['can_mark_for_handoff'])
                       or (isinstance(item_id, str) and handoff['allowed_actions'].get(item_id) == kind
                           and kind in {'read_context','accept_condition'}))
            if not allowed:
                raise StoreError('action_not_allowed')
            base = record['report']
            job = next(j for j in base['ranking']['jobs'] if j['job_id'] == action['job_id'])
            now = _now()
            versions = current_versions(base, job)
            if kind == 'confirm_requirements':
                reqs = Requirements.model_validate(job['requirements'])
                text = record['sources']['jobs'][job['job_id']]
                approval = requirements_review.approve(job['job_id'], text, reqs, now)
                checked = requirements_review.check(approval, job['job_id'], text, reqs)
                if checked.state != 'confirmed':
                    raise StoreError('invalid_approval')
                job['requirements_approval'] = approval.model_dump()
                job['requirements_review'] = checked.model_dump()
                checks = {j['job_id']:requirements_review.ApprovalCheck.model_validate(j['requirements_review'])
                          for j in base['ranking']['jobs']}
                base['requirements_review'] = requirements_review.summarize(base['ranking']['complete'], checks,
                    expected_ids=list(record['sources']['jobs'])).model_dump()
            decision = Decision(decision_id=uuid4().hex, job_id=job['job_id'], item_id=item_id, action=kind,
                                **versions, decided_by='recruiter', recorded_by='service', decided_at=now)
            record['decisions'].append(decision.model_dump())
            record['review_requests'][key] = fingerprint
            record.update(revision=record['revision']+1, updated_at=now)
            result = {'run':self._summary(record), 'report':self._view(record)}
            self._write(record)
            return result

    def delete(self, rid):
        with self._mutex:
            if self._read(rid)['state'] in ACTIVE:
                raise StoreError('run_active')
            tombstone = '.deleting-' + rid
            os.rename(rid, tombstone, src_dir_fd=self._rootfd, dst_dir_fd=self._rootfd)
            os.fsync(self._rootfd)
            self._remove_directory(tombstone)
