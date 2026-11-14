"""Own local privacy + synthetic contacts + optional real SDK/mock transport.

No live API calls; never reads .env. Prints only counts and fixed diagnostic codes.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def check():
    from prototype.privacy import local_privacy
    from prototype.privacy_core import POLICY_VERSION, REFERENCE
    async with local_privacy() as privacy:
        source = 'Иван Иванов. Телефон: +7 (999) 123-45-67. Email: ivan.synthetic@example.com. Разрабатывал на Python 3 года.'
        safe = await privacy.redact(source)
        await privacy.check(safe)  # Validate issued references before excluding their random nonces.
        plain = REFERENCE.sub('', safe)
        if any(value in plain for value in ('Иван', 'Иванов', '999', '123-45-67', 'ivan.synthetic@example.com')):
            raise RuntimeError('synthetic_contact_not_redacted')
        if len(privacy.issued_refs) < 3 or 'Разрабатывал на Python 3 года.' not in safe:
            raise RuntimeError('professional_text_missing')
        for text in ['Работала с SQL 1 год как с подрядчиком.', 'Создавала отчёты в Excel, где работала бухгалтером.']:
            protected = await privacy.redact(text)
            if ('SQL' in protected) or ('Excel' in protected):
                raise RuntimeError('ambiguous_organization_not_protected')
    return {'status':'pass', 'backend':POLICY_VERSION, 'synthetic_only':True, 'openai_network_calls':0}


async def check_model_boundary():
    from prototype.privacy_core import POLICY_VERSION
    import httpx
    from openai import AsyncOpenAI
    from prototype.application import analyze_protected
    from prototype.contracts import Requirements
    from prototype.analysis_contracts import ResumeAnalysis, VacancyAnalysis
    from prototype.demo import ReplayModel, demo_inputs
    from prototype.model import Budget, Model
    from prototype.privacy import local_privacy
    calls = []
    replay = ReplayModel()
    async def respond(request):
        body = json.loads(request.content)
        encoded = json.dumps(body, ensure_ascii=False)
        if any(value in encoded for value in ('Иван Иванов', 'ivan.synthetic@example.com', '999) 123', 'id123456', 'j_smith', '31 декабря 1990', 'info@localhost')):
            raise RuntimeError('synthetic_contact_in_payload')
        payload = json.loads(body['input'][1]['content'])
        task = payload['task']
        parsed = await replay.ask({'facts':ResumeAnalysis,'requirements':Requirements,'evaluation':VacancyAnalysis}[task], task, payload['data'])
        calls.append(task)
        return httpx.Response(200, request=request, json={
            'id':'resp_synthetic', 'object':'response', 'created_at':0, 'model':body['model'], 'status':'completed',
            'output':[{'type':'message', 'role':'assistant', 'id':'msg_synthetic', 'status':'completed',
                'content':[{'type':'output_text', 'text':parsed.model_dump_json(), 'annotations':[]}]}],
            'usage':{'input_tokens':10,'output_tokens':10,'total_tokens':20}})
    def factory(privacy):
        # Explicitly construct a transport-bound client: no real key or default HTTP transport.
        model = Model.__new__(Model)
        model.model, model.privacy = 'gpt-6-luna', privacy
        model.budget, model.usage = Budget(model.model), []
        model.client = AsyncOpenAI(api_key='synthetic-not-a-secret', max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
        return model
    resume, jobs = demo_inputs()
    resume = 'LinkedIn — j_smith\nГод рождения: 1990\nДень рождения: 31 декабря 1990\nEmail — info@localhost\nvk.com/id123456\nИван Иванов. Телефон: +7 (999) 123-45-67. Email: ivan.synthetic@example.com.\n' + resume
    with tempfile.TemporaryDirectory(prefix='privacy-mock-') as out:
        result = await analyze_protected(resume, jobs, privacy_context=local_privacy,
            model_factory=factory, out=Path(out))
        if result.exit_code != 0 or len(calls) != 7:
            return {'status':'failed', 'reason':'protected_mock_incomplete', 'openai_network_calls':0,
                    'mock_requests':len(calls), 'errors':[{'stage':e['stage'], 'code':e['code']} for e in result.report['errors']]}
    return {'status':'pass', 'backend':POLICY_VERSION, 'real_sdk':True, 'model_transport':'local_mock',
            'synthetic_only':True, 'openai_network_calls':0, 'mock_requests':len(calls),
            'completed_jobs':len(result.report['ranking']['jobs']), 'protected_live_verified':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models-dir', type=Path, default=Path('data/private/privacy-models'))
    parser.add_argument('--model-mock', action='store_true')
    args = parser.parse_args()
    os.environ['PRIVACY_MODELS_DIR'] = str(args.models_dir)
    from prototype.privacy import protect_dependency_logs
    from prototype.errors import error_code
    protect_dependency_logs()
    try:
        result = asyncio.run(check_model_boundary() if args.model_mock else check())
    except Exception as exc:
        result = {'status':'failed', 'code':error_code(exc), 'openai_network_calls':0}
    print(json.dumps(result))
    return 0 if result['status'] == 'pass' else 2


if __name__ == '__main__':
    raise SystemExit(main())
