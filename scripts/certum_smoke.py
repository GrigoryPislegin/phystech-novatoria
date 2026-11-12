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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', required=True, type=Path)
    parser.add_argument('--tenant-file', required=True, type=Path)
    parser.add_argument('--models-dir', required=True, type=Path)
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
        print(json.dumps(asyncio.run(check())))
        return 0
    except Exception as exc:
        # Never print exception messages, config, documents, response text or DSNs.
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__, 'openai_calls': 0}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
