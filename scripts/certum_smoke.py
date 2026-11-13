"""Real local Certum smoke on fictional contacts; no OpenAI calls or secret output.

Run with core's Python 3.12 environment, not the standalone CLI environment.
"""
import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def check():
    from prototype.privacy import certum_privacy

    async with certum_privacy() as privacy:
        source = 'Иван Иванов. Телефон: +7 (999) 123-45-67. Email: ivan.synthetic@example.com. Разрабатывал на Python 3 года.'
        safe = await privacy.redact(source)
        if any(value in safe for value in ('Иван', 'Иванов', '999', '123-45-67', 'ivan.synthetic@example.com')):
            raise RuntimeError('synthetic_contact_not_redacted')
        if len(privacy.issued_refs) < 3 or 'Разрабатывал на Python 3 года.' not in safe:
            raise RuntimeError('redaction_evidence_or_professional_text_missing')
        await privacy.check(safe)
        try:
            await privacy.redact('Контакт: contact#123')
        except RuntimeError as exc:
            if exc.args != ('privacy_untrusted_reference',):
                raise
        else:
            raise RuntimeError('untrusted_reference_accepted')
        return {'status': 'pass', 'real_certum': True, 'synthetic_only': True,
                'openai_calls': 0, 'redaction': 'pass', 'outbound_scan': 'pass',
                'untrusted_reference_block': 'pass'}


async def check_model_boundary():
    """Real core + real SDK + local synthetic transport. Never a live-model claim."""
    import tempfile
    import httpx
    from openai import AsyncOpenAI
    from prototype.application import analyze
    from prototype.contracts import Facts, Requirements, Evaluation
    from prototype.demo import ReplayModel, demo_inputs
    from prototype.model import Model
    from prototype.privacy import certum_privacy
    calls = []
    replay = ReplayModel()
    async def respond(request):
        body = json.loads(request.content)
        encoded = json.dumps(body, ensure_ascii=False)
        if any(value in encoded for value in ('Иван Иванов', 'ivan.synthetic@example.com', '999) 123')):
            raise RuntimeError('raw_synthetic_contact_in_payload')
        payload = json.loads(body['input'][1]['content'])
        task = payload['task']
        parsed = await replay.ask({'facts':Facts,'requirements':Requirements,'evaluation':Evaluation}[task], task, payload['data'])
        calls.append(task)
        return httpx.Response(200, request=request, json={
            'id':'resp_synthetic', 'object':'response', 'created_at':0, 'model':body['model'], 'status':'completed',
            'output':[{'type':'message', 'role':'assistant', 'id':'msg_synthetic', 'status':'completed',
                'content':[{'type':'output_text', 'text':parsed.model_dump_json(), 'annotations':[]}]}],
            'usage':{'input_tokens':10,'output_tokens':10,'total_tokens':20}})
    # Only a dummy key is used by this fresh smoke process and mock transport.
    os.environ['OPENAI_API_KEY'] = 'synthetic-mock-key-not-a-secret'
    async with certum_privacy() as privacy:
        model = Model('gpt-6-luna', privacy)
        await model.close()
        model.client = AsyncOpenAI(api_key='synthetic-mock-key-not-a-secret', max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
        resume, jobs = demo_inputs()
        resume = 'Иван Иванов. Телефон: +7 (999) 123-45-67. Email: ivan.synthetic@example.com.\n' + resume
        with tempfile.TemporaryDirectory(prefix='protected-mock-') as out:
            result = await analyze(resume, jobs, model_factory=lambda:model, privacy=privacy,
                out=Path(out), mode='synthetic_mock_transport_NOT_live_model')
            if result.exit_code != 0 or len(calls) != 7:
                return {'status':'failed', 'reason':'protected_mock_incomplete', 'openai_network_calls':0,
                        'mock_requests':len(calls),
                        'errors':[{'stage':e['stage'], 'code':e['code']} for e in result.report['errors']]}
    return {'status':'pass', 'real_certum':True, 'real_sdk':True, 'model_transport':'local_mock',
            'synthetic_only':True, 'openai_network_calls':0, 'mock_requests':len(calls),
            'completed_jobs':len(result.report['ranking']['jobs']), 'protected_live_verified':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', required=True, type=Path)
    parser.add_argument('--tenant-file', required=True, type=Path)
    parser.add_argument('--models-dir', required=True, type=Path)
    parser.add_argument('--model-mock', action='store_true', help='Настоящий core/SDK, локальные синтетические ответы вместо сети')
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    try:
        # Parse configuration as data, never source it as shell code.
        from dotenv import dotenv_values
        config = dotenv_values(args.env_file, interpolate=False)
        url = urlsplit(config.get('CERTUM_DATABASE_URL') or '')
        if (url.scheme != 'postgresql+psycopg' or url.hostname != '127.0.0.1'
                or url.port != 55439 or url.path != '/certum' or url.query or url.fragment):
            raise RuntimeError('only_isolated_loopback_database_allowed')
        for key in ('CERTUM_DATABASE_URL', 'CERTUM_MASTER_KEY'):
            if not config.get(key):
                raise RuntimeError('missing_private_configuration')
            os.environ[key] = config[key]
        os.environ['CERTUM_TENANT_ID'] = args.tenant_file.read_text().strip()
        os.environ['CERTUM_DETECTORS_MODELS_DIR'] = str(args.models_dir.resolve())
        result = asyncio.run(check_model_boundary() if args.model_mock else check())
        print(json.dumps(result))
        return 0 if result['status'] == 'pass' else 2
    except Exception as exc:
        # Never print exception messages, config, documents, response text or DSNs.
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__, 'openai_calls': 0}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
