"""Offline review examples on synthetic inputs. No secrets, core DB or APIs.

Run: .venv/bin/python docs/reviews/full_review_repro.py
True means the observed limitation/bug is present, not a successful safety test.
"""
import asyncio
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import runpy
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from prototype.contracts import Requirement, Requirements, Evaluation, Row
from prototype.demo import ReplayModel, SyntheticPrivacy
from prototype.documents import read_document
from prototype.pipeline import run_pipeline
from prototype.privacy import CertumPrivacy


async def references():
    findings = {}
    for name, whitespace in [('LF', '\n'), ('TAB', '\t')]:
        privacy = CertumPrivacy(SimpleNamespace(scan=AsyncMock(return_value=[])), None, None)
        privacy.issued_refs.add('человек#1')
        source = 'Навыки:' + whitespace + 'человек#1: Python'
        await privacy.check(source)
        try:
            await privacy.check(json.dumps({'text': source}, ensure_ascii=False))
        except RuntimeError as exc:
            findings[name] = exc.args == ('privacy_untrusted_reference',)
        else:
            findings[name] = False
    return findings


async def omission():
    class OmitGo(ReplayModel):
        async def ask(self, schema, task, payload):
            if task == 'requirements':
                return Requirements(items=[Requirement(id='r1', text='Python', quote='Python обязателен.',
                                                       mandatory_quote='Python обязателен.')])
            if task == 'evaluation':
                return Evaluation(rows=[Row(requirement_id='r1', status='full', fact_ids=['f1'],
                                            comment='Синтетическое подтверждение', question=None)])
            return await super().ask(schema, task, payload)
    report = await run_pipeline('Разрабатывал на Python 3 года. Использовал SQL 1 год.',
                                [('job-001', 'Python обязателен. Go обязателен.')], OmitGo(), SyntheticPrivacy())
    return report['ranking']['complete'] and report['ranking']['recommendation'] == 'review_top'


def documents():
    from docx import Document
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'synthetic.docx'
        d = Document()
        d.sections[0].header.paragraphs[0].text = 'Python обязателен.'
        d.add_paragraph('SQL желателен.')
        d.save(path)
        header_lost = 'Python' not in read_document(path)
        d = Document()
        d.add_paragraph('Разработчик')
        cell = d.add_table(rows=1, cols=1).cell(0, 0)
        cell.text = 'Требования'
        cell.add_table(rows=1, cols=1).cell(0, 0).text = 'Go обязателен.'
        d.save(path)
        return {'header_silently_lost': header_lost, 'nested_table_silently_lost': 'Go' not in read_document(path)}


def installer():
    script = Path(__file__).resolve().parents[2] / 'scripts/setup_agents.py'
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
        root = Path(tmp)
        (root/'scripts').mkdir()
        (root/'scripts/setup_agents.py').write_text(script.read_text())
        (root/'vendor/superpowers/skills').mkdir(parents=True)
        (root/'.codex').symlink_to(outside, target_is_directory=True)
        try:
            with patch('subprocess.check_output', return_value='22f0b463e7a5e579904dd6211a520321035526f7'), redirect_stdout(io.StringIO()):
                runpy.run_path(str(root/'scripts/setup_agents.py'), run_name='__main__')
        except SystemExit:
            pass
        return (Path(outside)/'config.toml').exists()


if __name__ == '__main__':
    print(json.dumps({'valid_ref_rejected_after_json': asyncio.run(references()),
                      'omitted_mandatory_requirement_still_complete': asyncio.run(omission()),
                      'docx': documents(), 'installer_wrote_outside_project': installer()}, ensure_ascii=False, indent=2))
