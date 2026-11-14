"""Local application service. Live is opt-in; default demos never use a network API."""
import asyncio
import base64
import hashlib
import json
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from .analysis_contracts import ResumeAnalysis, VacancyAnalysis
from .application import analyze, analyze_protected
from .contracts import Requirements
from .demo import ReplayModel, SyntheticPrivacy, demo_inputs
from .documents import MAX_BYTES, read_document_bytes, document_diagnostic
from .errors import ModelOutputError, error_code
from .model import Model, Budget
from .pipeline import RunControl
from .privacy import local_privacy, protect_dependency_logs
from .run_store import RunStore, StoreError, ACTIVE

MAX_TOTAL_BYTES = 18_700_000  # Leaves room for base64 and metadata in the 25 MB HTTP body.
UPLOAD_MOCK = 'synthetic-upload-mock'


def _uploaded_demo(resume, jobs):
    for scenario in ('success', 'disputed'):
        sample, vacancies = demo_inputs(scenario)
        if resume == sample and sorted(jobs) == sorted(text for _, text in vacancies):
            return scenario
    return None


class ScenarioReplay(ReplayModel):
    def __init__(self, scenario):
        super().__init__()
        self.scenario = scenario

    async def ask(self, schema, task, payload):
        if self.scenario == 'incomplete' and task == 'requirements' and 'Java' in payload['text']:
            raise ModelOutputError('synthetic_incomplete_case')
        return await super().ask(schema, task, payload)


class SyntheticSDKModel(Model):
    """Real SDK with an explicitly local mock transport and no credential lookup."""
    def __init__(self, privacy, scenario):
        import httpx
        from openai import AsyncOpenAI
        self.model, self.privacy = 'gpt-6-luna', privacy
        self.budget, self.usage = Budget(self.model), []
        replay = ReplayModel()

        async def respond(request):
            body = json.loads(request.content)
            payload = json.loads(body['input'][1]['content'])
            task = payload['task']
            schema = {'facts':ResumeAnalysis, 'requirements':Requirements, 'evaluation':VacancyAnalysis}[task]
            if scenario == 'incomplete' and task == 'requirements' and 'Java' in payload['data']['text']:
                # A schema-invalid response exercises validation/recovery, not a
                # transport exception (which the SDK wraps as a connection error).
                output = '{"items":"synthetic-invalid-response"}'
            else:
                value = await replay.ask(schema, task, payload['data'])
                if scenario == 'disputed' and task == 'evaluation':
                    for row in value.rows:
                        if row.status == 'partial':
                            row.comment = 'Python подтверждён. Второй навык не указан.'
                            row.question = 'Уточните опыт по второй части требования.'
                output = value.model_dump_json()
            return httpx.Response(200, request=request, json={
                'id':'resp_synthetic', 'object':'response','created_at':0,'model':self.model,'status':'completed',
                'output':[{'type':'message','role':'assistant','id':'msg_synthetic','status':'completed',
                           'content':[{'type':'output_text','text':output,'annotations':[]}]}],
                'usage':None})
        self.client = AsyncOpenAI(api_key='synthetic-not-a-secret', max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))


class LocalService:
    def __init__(self, root, *, allow_live=False):
        protect_dependency_logs()
        self.root = Path(root)
        self.store = RunStore(self.root / 'runs')
        self.work = self.root / 'work'
        if self.work.is_symlink():
            self.store.close()
            raise StoreError('unsafe_path')
        self.work.mkdir(mode=0o700, exist_ok=True)
        os.chmod(self.work, 0o700)
        self.allow_live = bool(allow_live)
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='analysis')
        self._controls, self._futures, self._inputs = {}, {}, {}

    @property
    def capabilities(self):
        return {'modes':['synthetic-replay','synthetic-protected-mock',UPLOAD_MOCK] +
                        (['protected-live'] if self.allow_live else []),
                'scenarios':['success','disputed','incomplete'],
                'operations':['create','list','read','cancel','delete','review','inspect','compare'],
                'live':self.allow_live, 'max_files':21, 'max_file_bytes':MAX_BYTES, 'max_total_bytes':MAX_TOTAL_BYTES}

    def close(self):
        with self._lock:
            for control in self._controls.values():
                control.cancel()
        self._pool.shutdown(wait=True, cancel_futures=False)
        self._inputs.clear()
        self.store.close()

    def inspect(self, payload):
        if not isinstance(payload, dict) or set(payload) != {'resume','jobs'}:
            raise StoreError('input_invalid')
        jobs = payload['jobs']
        if not isinstance(jobs, list) or not 1 <= len(jobs) <= 20:
            raise StoreError('invalid_job_set')
        entries, total = [], 0
        for file in [payload['resume'], *jobs]:
            if not isinstance(file, dict) or set(file) != {'name','content_base64'}:
                raise StoreError('input_invalid')
            name, encoded = file['name'], file['content_base64']
            if not isinstance(name, str) or not 1 <= len(name) <= 255 or any(c in name for c in ('/','\\','\0')):
                raise StoreError('input_invalid')
            suffix = Path(name).suffix.lower()
            if not isinstance(encoded, str):
                raise StoreError('input_invalid')
            if len(encoded) > 4 * ((MAX_BYTES + 2) // 3):
                raise StoreError('input_too_large')
            try:
                raw = base64.b64decode(encoded, validate=True)
            except (ValueError, UnicodeError):
                raise StoreError('input_invalid') from None
            total += len(raw)
            if len(raw) > MAX_BYTES or total > MAX_TOTAL_BYTES:
                raise StoreError('input_too_large')
            entries.append((suffix, raw))
        results, texts = [], []
        for index, (suffix, raw) in enumerate(entries):
            result = {'role':'resume' if index == 0 else 'vacancy', 'index':1 if index == 0 else index}
            try:
                text = read_document_bytes(raw, suffix)
                texts.append(text)
                result.update(status='ok', characters=len(text))
            except Exception as exc:
                texts.append(None)
                diagnostic = document_diagnostic(exc)
                result.update(status='error', error=diagnostic['code'], reason=diagnostic['reason'],
                              action=diagnostic['action'])
            results.append(result)
        if any(result['status'] == 'error' for result in results):
            return {'input_id':None, 'ready':False, 'files':results}
        resume, *vacancies = texts
        mock_scenario = _uploaded_demo(resume, vacancies)
        input_id = None
        if self.allow_live or mock_scenario:
            input_id = uuid4().hex
            with self._lock:
                self._expire_inputs()
                while len(self._inputs) >= 20:
                    self._inputs.pop(next(iter(self._inputs)))
                jobs = [('job-' + hashlib.sha256(text.encode()).hexdigest()[:24] + '-' + str(index), text)
                        for index, text in enumerate(vacancies, 1)]
                self._inputs[input_id] = (time.monotonic(), (resume, jobs), mock_scenario)
        return {'input_id':input_id, 'ready':True, 'files':results, 'mock_scenario':mock_scenario}

    def _expire_inputs(self):
        for key, (created, _, _) in list(self._inputs.items()):
            if time.monotonic() - created >= 900:
                self._inputs.pop(key)

    def create(self, request):
        if not isinstance(request, dict) or not isinstance(request.get('mode'), str):
            raise StoreError('invalid_request')
        mode = request['mode']
        scenario = None
        upload = mode in {'protected-live', UPLOAD_MOCK}
        if upload:
            if mode == 'protected-live' and not self.allow_live:
                raise StoreError('live_disabled')
            fields = {'mode','input_id','idempotency_key'}
            if set(request) != (fields | {'budget'} if mode == 'protected-live' else fields):
                raise StoreError('invalid_request')
            budget = request.get('budget')
            if mode == 'protected-live' and (type(budget) not in {float,int} or not 0 < budget <= 1):
                raise StoreError('invalid_budget')
            if not isinstance(request['input_id'], str):
                raise StoreError('input_not_found')
        elif mode in {'synthetic-replay','synthetic-protected-mock'}:
            if (set(request) != {'mode','scenario','idempotency_key'} or not isinstance(request['scenario'], str)
                    or request['scenario'] not in {'success','disputed','incomplete'}):
                raise StoreError('invalid_request')
            scenario = request['scenario']
            inputs = demo_inputs('disputed' if scenario == 'disputed' else 'success')
            if mode == 'synthetic-protected-mock':
                inputs = ('Иван Иванов. Телефон: +7 (999) 123-45-67. Email: ivan.synthetic@example.com.\n' + inputs[0], inputs[1])
        else:
            raise StoreError('invalid_mode')
        with self._lock:
            fields = {k:v for k,v in request.items() if k != 'idempotency_key'}
            key = request['idempotency_key']
            if upload:
                existing = self.store.lookup_request(fields, key)
                if existing is not None:
                    return existing
                self._expire_inputs()
                cached = self._inputs.get(request['input_id'])
                if cached is None:
                    raise StoreError('input_not_found')
                _, inputs, mock_scenario = cached
                if mode == UPLOAD_MOCK:
                    if mock_scenario is None:
                        raise StoreError('mock_requires_demo_documents')
                    scenario = mock_scenario
            summary, created = self.store.create(fields | {'total':len(inputs[1])}, key, scenario=scenario)
            if created:
                if upload:
                    self._inputs.pop(request['input_id'], None)
                rid = summary['run_id']
                control = RunControl(progress=lambda event:self.store.progress(rid, event))
                self._controls[rid] = control
                execution = fields | {'scenario': scenario or 'success'}
                self._futures[rid] = self._pool.submit(self._execute, rid, execution, inputs, control)
            return summary

    def _execute(self, rid, request, inputs, control):
        snapshot = {}
        def capture(value):
            snapshot.update(value)
        try:
            self.store.start(rid)
            with tempfile.TemporaryDirectory(prefix='analysis-', dir=self.work) as directory:
                mode, scenario = request['mode'], request.get('scenario', 'success')
                if mode == 'synthetic-replay':
                    result = asyncio.run(analyze(*inputs, model_factory=lambda:ScenarioReplay(scenario),
                        privacy=SyntheticPrivacy(), out=Path(directory), control=control,
                        mode='synthetic_replay_NOT_model_output', source_sink=capture))
                else:
                    mock = mode in {'synthetic-protected-mock', UPLOAD_MOCK}
                    result = asyncio.run(analyze_protected(*inputs, privacy_context=local_privacy,
                        model_factory=(lambda p:SyntheticSDKModel(p, scenario)) if mock else
                                      (lambda p:Model('gpt-6-luna', p, request['budget'])),
                        out=Path(directory), control=control, source_sink=capture,
                        mode='synthetic_sdk_mock_NOT_model_output' if mock else 'live_local_privacy'))
                    if mock:
                        result.report.update(model_transport='local_mock', openai_network_calls=0,
                                             usage_measurement='not_measured_synthetic_response')
                if mode != 'protected-live':
                    result.report['demo_scenario'] = scenario
                self.store.finish(rid, result.report, snapshot)
        except Exception as exc:
            self.store.fail(rid, error_code(exc))
        finally:
            snapshot.clear()
            with self._lock:
                self._controls.pop(rid, None)
                self._futures.pop(rid, None)

    def wait(self, rid, timeout=30):
        future = self._futures.get(rid)
        if future is not None:
            future.result(timeout=timeout)
        return self.store.get(rid)

    def cancel(self, rid):
        with self._lock:
            summary = self.store.get(rid)
            if summary['state'] not in ACTIVE:
                return summary
            control = self._controls.get(rid)
            if control is None:
                raise StoreError('run_unavailable')
            control.cancel()
            return self.store.request_cancel(rid)
