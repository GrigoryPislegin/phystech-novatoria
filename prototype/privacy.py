"""Adapter for Gleb's actual core. No regex fallback and no external relay."""
import os
import re
import uuid
from contextlib import asynccontextmanager

# Matches core's reference grammar at reviewed revision 156c229.
# This rejects untrusted references; it is NOT a replacement PII detector.
REF_TOKEN = re.compile(r'[A-Za-zА-Яа-яЁё_]+#\d+')


class CertumPrivacy:
    def __init__(self, detectors, scope, source):
        self.detectors, self.scope, self.source = detectors, scope, source
        self.issued_refs = set()

    async def redact(self, text):
        # Core treats references as protected spans. Raw inputs cannot claim that privilege.
        if REF_TOKEN.search(text):
            raise RuntimeError('privacy_untrusted_reference')
        result = await self.detectors.redact(self.scope, text, source=self.source)
        self.issued_refs.update(r.ref for r in result.replacements)
        await self.check(result.text)
        return result.text

    async def check(self, text):
        if not set(REF_TOKEN.findall(text)) <= self.issued_refs:
            raise RuntimeError('privacy_untrusted_reference')
        # Stricter than core gateway's is_definite: NER-only findings also stop this prototype.
        if await self.detectors.scan(self.scope, text):
            raise RuntimeError('privacy_residual_findings')


@asynccontextmanager
async def certum_privacy():
    required = ('CERTUM_DATABASE_URL', 'CERTUM_MASTER_KEY', 'CERTUM_TENANT_ID')
    if not all(os.environ.get(k) for k in required):
        raise RuntimeError('certum_configuration_missing')
    engine = None
    try:
        from certum_core.core.settings import Settings
        from certum_core.core.types import Source
        from certum_core.db import make_engine, tenant_scope
        from certum_core.detectors import build_detectors
        from certum_core.detectors.settings import DetectorSettings
        from certum_core.entities import build_entities
        from certum_core.vault import build_vault
        settings = Settings(_env_file=None)
        engine = make_engine(settings.database_url)
        detectors = build_detectors(build_entities(build_vault(settings)),
                                    settings=DetectorSettings(_env_file=None, ner=True))
        detectors.warmup()
        async with tenant_scope(engine, uuid.UUID(os.environ['CERTUM_TENANT_ID'])) as scope:
            await scope.assert_tenant()
            # Force tenant/vault readiness before network access even on documents with no findings.
            await build_vault(settings).cipher(scope)
            yield CertumPrivacy(detectors, scope, Source.file)
    finally:
        if engine is not None:
            await engine.dispose()
