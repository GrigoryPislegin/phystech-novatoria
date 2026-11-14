"""Vanya PR23 document delivery: actual PDF/DOCX parsing, bound to synthetic E6."""
import hashlib
import json
from pathlib import Path
import unittest

from prototype.documents import read_document

ROOT = Path(__file__).resolve().parents[2]


class E6DocumentTests(unittest.TestCase):
    def test_all_nine_documents_match_manifest_and_current_synthetic_sources(self):
        folder = ROOT / 'evaluation' / 'fixtures' / 'documents'
        manifest = json.loads((folder / 'manifest.json').read_text())
        self.assertEqual(manifest['origin'], 'synthetic')
        records = manifest['documents']
        self.assertEqual(len(records), 9)
        cases = json.loads((ROOT / 'evaluation/expectations/egor/e6-cases.json').read_text())['cases']
        resumes = {case['case_id']: case['cv_text'] for case in cases}
        jobs = {}
        for case in cases:
            for job in case['vacancies']:
                jobs.setdefault(job['job_id'], set()).add(job['text'])
        for record in records:
            with self.subTest(file=record['file']):
                path = folder / record['file']
                self.assertEqual(path.parent, folder)
                self.assertFalse(path.is_symlink())
                text = read_document(path)
                self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), record['text_sha256'])
                if record['kind'] == 'resume':
                    self.assertEqual(text, resumes[record['id']])
                else:
                    self.assertEqual(record['kind'], 'vacancy')
                    self.assertIn(text, jobs[record['id']])
