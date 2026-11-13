import asyncio
from contextlib import asynccontextmanager, redirect_stdout
import io
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from prototype.__main__ import execute
from prototype.contracts import Facts
from prototype.demo import ReplayModel, SyntheticPrivacy, demo_inputs
from prototype.model import Budget, Model
from prototype.pipeline import RunControl, run_pipeline


class ReviewRegressions(unittest.TestCase):
    def test_pdf_warning_cannot_log_document_operand(self):
        stream=b'BT /F1 12 Tf 72 720 Td (Hello) Tj ET\n (DOCUMENT_LOG_CANARY_987) w\n'
        objects=[b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
                 b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
                 b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
                 b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'endstream']
        pdf=b'%PDF-1.4\n'; offsets=[]
        for i,obj in enumerate(objects,1):
            offsets.append(len(pdf)); pdf+=f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
        start=len(pdf)
        pdf+=b'xref\n0 6\n0000000000 65535 f \n'+b''.join(f'{o:010} 00000 n \n'.encode() for o in offsets)
        pdf+=b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n'+str(start).encode()+b'\n%%EOF\n'
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'synthetic.pdf'; path.write_bytes(pdf)
            p=subprocess.run([sys.executable, '-m','prototype','inspect',str(path)],capture_output=True,text=True,timeout=15)
            self.assertEqual(p.returncode,0)
            self.assertNotIn('DOCUMENT_LOG_CANARY_987',p.stdout+p.stderr)

    def test_cancel_during_scan_prevents_reserve_and_request(self):
        control=RunControl()
        async def checking(text):
            await asyncio.sleep(0)
            control.cancel()
        model=Model.__new__(Model)
        model.model,model.privacy='gpt-6-luna',SimpleNamespace(check=checking)
        model.budget,model.usage=Budget(model.model),[]
        model.client=SimpleNamespace(responses=SimpleNamespace(parse=AsyncMock(return_value=
            SimpleNamespace(status='completed',usage=None,output_parsed=Facts(items=[])))))
        report=asyncio.run(run_pipeline(*demo_inputs(),model,SyntheticPrivacy(),control=control))
        self.assertEqual(model.budget.calls,0)
        model.client.responses.parse.assert_not_called()
        self.assertEqual(report['errors'][0]['code'],'cancelled')

    def inputs(self, root, deadline=300):
        resume,jobs=demo_inputs(); cv=root/'cv.txt'; cv.write_text(resume)
        folder=root/'jobs'; folder.mkdir()
        for i,(_,text) in enumerate(jobs): (folder/f'{i}.txt').write_text(text)
        return SimpleNamespace(command='run',resume=cv,jobs=folder,out=root/'out',deadline=deadline,
                               model='gpt-6-luna',budget=1)

    def test_privacy_startup_is_bounded_by_async_deadline(self):
        @asynccontextmanager
        async def slow():
            await asyncio.sleep(0.2)
            yield SyntheticPrivacy()
        with tempfile.TemporaryDirectory() as tmp:
            args=self.inputs(Path(tmp),deadline=0.02)
            start=time.monotonic()
            with patch('prototype.__main__.certum_privacy',slow):
                with self.assertRaisesRegex(RuntimeError,'deadline_exceeded'): asyncio.run(execute(args))
            self.assertLess(time.monotonic()-start,0.15)

    def test_failed_vault_commit_does_not_publish_report_or_success_path(self):
        @asynccontextmanager
        async def failure():
            yield SyntheticPrivacy()
            raise RuntimeError('synthetic_commit_failed')
        with tempfile.TemporaryDirectory() as tmp:
            args=self.inputs(Path(tmp))
            output=io.StringIO()
            with patch('prototype.__main__.certum_privacy',failure), \
                 patch('prototype.__main__.Model',return_value=ReplayModel()), redirect_stdout(output):
                with self.assertRaisesRegex(RuntimeError,'synthetic_commit_failed'): asyncio.run(execute(args))
            self.assertEqual(list(args.out.iterdir()),[])
            self.assertNotIn('Отчёт:',output.getvalue())
