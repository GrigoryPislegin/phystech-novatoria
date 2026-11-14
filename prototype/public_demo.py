"""Passwordless browser workspaces with one persistent, shared demo budget."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import threading

from .local_service import LocalService
from .run_store import ACTIVE, KEY, StoreError

COOKIE = '__Host-recruiter-demo'
TOKEN = re.compile(r'[0-9a-f]{64}\Z')


@dataclass
class Visitor:
    token: str
    csrf: str
    service: LocalService | None = None


class PublicDemo:
    def __init__(self, root, limit, *, service_factory=LocalService, max_visitors=64):
        self.limit = Decimal(str(limit))
        if not self.limit.is_finite() or not 0 < self.limit <= 100:
            raise StoreError('invalid_demo_budget')
        self.root = Path(root)
        if self.root.is_symlink():
            raise StoreError('unsafe_path')
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self.factory, self.max_visitors = service_factory, max_visitors
        self.visitors = {}
        self.leases = {}
        self.lock = threading.RLock()
        self.inspect_gate = threading.BoundedSemaphore(1)
        secret_file = self.root / 'session.key'
        if secret_file.is_symlink():
            raise StoreError('unsafe_path')
        if not secret_file.exists():
            fd = os.open(secret_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(secrets.token_bytes(32))
        self.secret = secret_file.read_bytes()
        if len(self.secret) != 32:
            raise StoreError('invalid_demo_ledger')
        ledger = self.root / 'budget.json'
        if ledger.is_symlink():
            raise StoreError('unsafe_path')
        if ledger.exists():
            self.entries = json.loads(ledger.read_text())['entries']
            if not isinstance(self.entries, list):
                raise StoreError('invalid_demo_ledger')
            for entry in self.entries:
                amount = Decimal(entry['amount'])
                if (not amount.is_finite() or not 0 <= amount <= 1
                        or not TOKEN.fullmatch(entry['visitor'])):
                    raise StoreError('invalid_demo_ledger')
        else:
            if any(TOKEN.fullmatch(p.name) for p in self.root.iterdir()):
                raise StoreError('missing_demo_ledger')
            self.entries = []
            self._save()

    def _save(self):
        path = self.root / ('.budget-' + secrets.token_hex(8))
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump({'version':1, 'entries':self.entries}, stream, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(path, self.root / 'budget.json')
            directory = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            path.unlink(missing_ok=True)

    def _signature(self, token):
        return hmac.new(self.secret, ('cookie:' + token).encode(), 'sha256').hexdigest()

    def cookie(self, visitor):
        return visitor.token + '.' + self._signature(visitor.token)

    def _identity(self, token):
        csrf = hmac.new(self.secret, ('csrf:' + token).encode(), 'sha256').hexdigest()
        return self.visitors.get(token) or Visitor(token, csrf)

    def _load(self, token):
        if token not in self.visitors:
            if len(self.visitors) >= self.max_visitors:
                # Only resident services are capped. Saved histories are never erased.
                for old_token, old in list(self.visitors.items()):
                    if not self.leases.get(old_token) and not any(r['state'] in ACTIVE for r in old.service.store.list()):
                        old.service.close()
                        del self.visitors[old_token]
                        break
                else:
                    raise StoreError('demo_capacity')
            visitor = self._identity(token)
            visitor.service = self.factory(self.root / token, allow_live=True)
            self.visitors[token] = visitor
        return self.visitors[token]

    def visitor(self, cookie, *, create=False):
        with self.lock:
            if isinstance(cookie, str):
                token, sep, signature = cookie.partition('.')
                if sep and TOKEN.fullmatch(token) and TOKEN.fullmatch(signature) and hmac.compare_digest(signature, self._signature(token)):
                    return self._identity(token), False
            if not create:
                raise StoreError('session_required')
            # Bootstrap does not allocate a directory, cache or worker.
            return self._identity(secrets.token_hex(32)), True

    def service(self, visitor, *, create=False):
        with self.lock:
            if not create and not (self.root / visitor.token).is_dir():
                return None
            return self._load(visitor.token).service

    def hold(self, visitor):
        with self.lock:
            self.leases[visitor.token] = self.leases.get(visitor.token, 0) + 1

    def release(self, visitor):
        with self.lock:
            count = self.leases.get(visitor.token, 1) - 1
            if count:
                self.leases[visitor.token] = count
            else:
                self.leases.pop(visitor.token, None)

    def inspect(self, visitor, payload):
        with self.lock:
            service = self.service(visitor, create=True)
            # At most eight input batches across every visitor, not eight per visitor.
            batches = []
            for active in self.visitors.values():
                with active.service._lock:
                    active.service._expire_inputs()
                    batches.extend((created, active.service, key) for key, (created, _) in active.service._inputs.items())
            for _, owner, key in sorted(batches, key=lambda b:b[0])[:max(0, len(batches) - 7)]:
                with owner._lock:
                    owner._inputs.pop(key, None)
        return service.inspect(payload)

    def _settle(self):
        changed = False
        for entry in self.entries:
            if entry['settled'] or entry['run_id'] is None:
                continue
            service = self._load(entry['visitor']).service
            try:
                run = service.store.get(entry['run_id'])
                if run['state'] in ACTIVE:
                    continue
                amount = Decimal(str(service.store.report(entry['run_id'])['reserved_usd_estimate']))
                if not amount.is_finite() or not 0 <= amount <= Decimal(entry['amount']):
                    continue
                entry['amount'] = str(amount)
            except (StoreError, ValueError, KeyError, InvalidOperation):
                # An interrupted/deleted/unmeasured call keeps its full reserve.
                pass
            entry['settled'] = True
            changed = True
        if changed:
            self._save()

    def create(self, visitor, request):
        if (not isinstance(request, dict) or set(request) != {'mode','input_id','budget','idempotency_key'}
                or request['mode'] != 'protected-live'
                or not isinstance(request['input_id'], str) or not re.fullmatch(r'[0-9a-f]{32}', request['input_id'])
                or not isinstance(request['idempotency_key'], str) or not KEY.fullmatch(request['idempotency_key'])
                or type(request['budget']) not in {int, float} or not 0 < request['budget'] <= 1):
            raise StoreError('invalid_request')
        digest = hashlib.sha256(json.dumps(request, sort_keys=True, allow_nan=False).encode()).hexdigest()
        with self.lock:
            visitor = self._load(visitor.token)
            self._settle()
            for entry in self.entries:
                if entry['visitor'] == visitor.token and entry['key'] == request['idempotency_key']:
                    if entry['digest'] != digest:
                        raise StoreError('idempotency_conflict')
                    if entry['run_id'] is None:
                        restored = visitor.service.store.lookup_request(
                            {k:v for k,v in request.items() if k != 'idempotency_key'} |
                            {'budget':float(Decimal(entry['amount']))}, request['idempotency_key'])
                        if restored is None:
                            raise StoreError('run_unavailable')
                        entry['run_id'] = restored['run_id']
                        self._save()
                        self._settle()
                    return visitor.service.store.get(entry['run_id'])
            if any(run['state'] in ACTIVE for v in self.visitors.values() for run in v.service.store.list()):
                raise StoreError('busy')
            remaining = self.limit - sum((Decimal(e['amount']) for e in self.entries), Decimal(0))
            if remaining <= 0:
                raise StoreError('demo_budget_exhausted')
            amount = min(Decimal(str(request['budget'])), remaining)
            entry = {'visitor':visitor.token, 'key':request['idempotency_key'], 'digest':digest,
                     'amount':str(amount), 'settled':False, 'run_id':None}
            self.entries.append(entry)
            self._save()  # Reserve before dispatch; a crash cannot reset the budget.
            try:
                run = visitor.service.create({**request, 'budget':float(amount)})
            except StoreError:
                self.entries.remove(entry)  # Rejected before a model run was dispatched.
                self._save()
                raise
            entry['run_id'] = run['run_id']
            self._save()
            return run

    def before_delete(self):
        with self.lock:
            self._settle()

    def close(self):
        for visitor in self.visitors.values():
            visitor.service.close()
        with self.lock:
            # Closing may interrupt a call. Reservations already on disk remain.
            self._save()
