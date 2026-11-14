"""E13 harness: synthetic fixtures → real OpenAI SDK over httpx.MockTransport → Model.ask → pipeline → report.

No test cases live here. Nothing is sent anywhere: the SDK client is bound to a local MockTransport,
needs no key and reads no `.env`. The "model answers" are handwritten and say nothing about LLM quality.

A fixture is written against the ORIGINAL synthetic documents. The pipeline shows the model the
text after the privacy step, so every quote is projected onto that processed text first, the way a
model can only quote what it was shown. Free-text fields (fact text, requirement text, comment,
question, claim text, note) are passed on as written: they are what a model writes freely, and the
privacy check of the answer applies to them as it does in a live run.

`faults` change single answers to reproduce failures:
    {'facts': 'not_json' | 'schema'}                     the facts answer is rejected
    {'job': {'<job_id>': 'not_json'}}                    one vacancy's evaluation is rejected
    {'edit': callable(task, job_id, answer_dict)}        arbitrary edit of an answer before it is sent
"""
import asyncio
import copy
import difflib
import json
import os
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'evaluation' / 'fixtures' / 'integration'
EXPECTATIONS = ROOT / 'evaluation' / 'expectations' / 'egor'
# The same variable `prototype.privacy.local_privacy` reads; in the Docker image the weights are in /opt/privacy-models.
MODELS = Path(os.environ.get('PRIVACY_MODELS_DIR', ROOT / 'data' / 'private' / 'privacy-models'))


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / f'egor-e13-{name}.json').read_text(encoding='utf-8'))


def real_privacy_available() -> bool:
    """Public NER weights and their libraries are present (they are in the Docker image)."""
    if not (MODELS / 'slovnet_ner_news_v1.tar').is_file():
        return False
    try:
        import navec  # noqa: F401
        import slovnet  # noqa: F401
    except ImportError:
        return False
    return True


REFERENCE = re.compile(r'\[\[PRIV:[a-f0-9]{16}:\d+:[A-Z]+\]\]')


class Projector:
    """Maps a fragment of the original text onto the processed text the model was shown.

    The processed text is the original with some spans replaced by privacy references. The plain
    pieces between references are located in the original in order, which gives exact pairs of
    equal blocks; a fragment that touches a masked span takes the whole reference, never a part
    of it. Without references the two texts must be equal."""

    def __init__(self, original: str, processed: str):
        self.original, self.processed = original, processed
        self.blocks, cursor, position = [], 0, 0  # (original start, processed start, length)
        for piece in REFERENCE.split(processed):
            found = original.find(piece, cursor) if piece else cursor
            if found < 0:
                raise ValueError('processed_text_not_alignable')
            start = processed.index(piece, position) if piece else position
            self.blocks.append((found, start, len(piece)))
            cursor, position = found + len(piece), start + len(piece)
            reference = REFERENCE.match(processed, position)
            position = reference.end() if reference else position

    def _at(self, position: int, end: bool) -> int:
        for index, (a, b, length) in enumerate(self.blocks):
            inside = a < position <= a + length if end else a <= position < a + length
            if inside or (length == 0 and position == a):
                return b + position - a
            if position < a or (end and position == a):  # in the masked span before this block
                previous = self.blocks[index - 1] if index else (0, 0, 0)
                return b if end else previous[1] + previous[2]
        return len(self.processed)

    def quote(self, fragment: str) -> str:
        start = self.original.find(fragment)
        if start < 0:  # not in the original at all: sent as written, the pipeline must reject it
            return fragment
        return self.processed[self._at(start, False):self._at(start + len(fragment), True)]


def _project(value, projector: Projector, keys=('quote', 'mandatory_quote', 'vacancy_quote')):
    if isinstance(value, dict):
        return {k: (projector.quote(v) if k in keys and isinstance(v, str) else _project(v, projector, keys))
                for k, v in value.items()}
    if isinstance(value, list):
        return [_project(v, projector, keys) for v in value]
    return value


class Replay:
    """Answers the three pipeline tasks from one fixture. Counts requests; never opens a socket."""

    def __init__(self, fixture: dict, faults: dict | None = None):
        self.fixture, self.faults = fixture, faults or {}
        self.requests: list[tuple[str, str | None]] = []
        self.outbound: list[str] = []  # every request body as the SDK was about to send it
        self.cv_projector: Projector | None = None

    def _job(self, text: str) -> dict:
        """The fixture vacancy whose text the processed payload text came from."""
        return max(self.fixture['vacancies'],
                   key=lambda v: difflib.SequenceMatcher(None, v['text'], text, autojunk=False).ratio())

    def answer(self, task: str, data: dict) -> tuple[str, str | None]:
        model = self.fixture['model']
        if task == 'facts':
            self.cv_projector = Projector(self.fixture['cv_text'], data['text'])
            job_id, answer = None, _project(copy.deepcopy(model['facts']), self.cv_projector, keys=('quote',))
            fault = self.faults.get('facts')
        else:
            vacancy = self._job(data['text'] if task == 'requirements' else data['vacancy_text'])
            job_id = vacancy['job_id']
            projector = Projector(vacancy['text'], data['text'] if task == 'requirements' else data['vacancy_text'])
            answer = copy.deepcopy(model[task][job_id])
            if task == 'requirements':
                answer = _project(answer, projector, keys=('quote', 'mandatory_quote'))
            else:  # condition quotes: the CV side comes from the CV, the vacancy side from the vacancy
                for item in answer['conditions']['items']:
                    if item.get('cv'):
                        item['cv']['quote'] = self.cv_projector.quote(item['cv']['quote'])
                    if item.get('vacancy_quote'):
                        item['vacancy_quote'] = projector.quote(item['vacancy_quote'])
            fault = self.faults.get('job', {}).get(job_id) if task == 'evaluation' else None
        self.requests.append((task, job_id))
        if 'edit' in self.faults:
            self.faults['edit'](task, job_id, answer)
        if fault == 'not_json':
            return 'not a json answer', job_id
        if fault == 'schema':
            return json.dumps({'unexpected': True}), job_id
        return json.dumps(answer, ensure_ascii=False), job_id

    def model_factory(self, privacy):
        import httpx
        from openai import AsyncOpenAI
        from prototype.model import Budget, Model

        async def respond(request):
            body = json.loads(request.content)
            self.outbound.append(json.dumps(body, ensure_ascii=False))
            payload = json.loads(body['input'][1]['content'])
            text, _ = self.answer(payload['task'], payload['data'])
            return httpx.Response(200, request=request, json={
                'id': 'resp_synthetic', 'object': 'response', 'created_at': 0, 'model': body['model'],
                'status': 'completed',
                'output': [{'type': 'message', 'role': 'assistant', 'id': 'msg_synthetic', 'status': 'completed',
                            'content': [{'type': 'output_text', 'text': text, 'annotations': []}]}],
                'usage': {'input_tokens': 10, 'output_tokens': 10, 'total_tokens': 20}})

        model = Model.__new__(Model)  # no key, no default transport: the client is bound to the mock
        model.model, model.privacy = 'gpt-6-luna', privacy
        model.budget, model.usage = Budget(model.model), []
        model.client = AsyncOpenAI(api_key='synthetic-not-a-secret', max_retries=0,
                                   http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
        return model


class Passthrough:
    """No privacy processing: checks the contracts and the pipeline on the original synthetic text."""

    async def redact(self, text):
        return text

    async def check(self, text):
        return None


def run(fixture: dict, *, privacy: str = 'passthrough', faults: dict | None = None) -> tuple[dict, Replay]:
    """One pipeline run. privacy: 'passthrough' or 'local' (the real privacy_core with public NER weights)."""
    from prototype.application import analyze, analyze_protected
    replay = Replay(fixture, faults)
    jobs = [(v['job_id'], v['text']) for v in fixture['vacancies']]

    async def go(out: Path):
        if privacy == 'local':
            from prototype.privacy import local_privacy
            return await analyze_protected(fixture['cv_text'], jobs, privacy_context=local_privacy,
                                           model_factory=replay.model_factory, out=out,
                                           mode='synthetic_sdk_mock_NOT_model_output')
        guard = Passthrough()
        return await analyze(fixture['cv_text'], jobs, model_factory=lambda: replay.model_factory(guard),
                             privacy=guard, out=out, mode='synthetic_sdk_mock_NOT_model_output')

    with tempfile.TemporaryDirectory(prefix='e13-') as out:
        result = asyncio.run(go(Path(out)))
    return result.report, replay


def statuses(report: dict) -> dict:
    """{job_id: {requirement quote: status}} of a report."""
    return {j['job_id']: {r['quote']: next(x['status'] for x in j['evaluation']['rows'] if x['requirement_id'] == r['id'])
                          for r in j['requirements']['items']} for j in report['ranking']['jobs']}
