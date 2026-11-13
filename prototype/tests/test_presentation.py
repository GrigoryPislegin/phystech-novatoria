import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from prototype.demo import ReplayModel, SyntheticPrivacy, demo_inputs
from prototype.pipeline import run_pipeline, write_report


class PresentationTests(unittest.TestCase):
    def test_invented_model_prose_is_not_a_source_backed_manager_brief(self):
        class Invented(ReplayModel):
            async def ask(self, schema, task, payload):
                result = await super().ask(schema, task, payload)
                if task == 'evaluation':
                    for row in result.rows:
                        row.comment = 'Опыт 99 лет в ВЫДУМАННАЯ_КОМПАНИЯ'
                        if row.status != 'full': row.question = 'Какова ваша национальность?'
                return result
        report = asyncio.run(run_pipeline(*demo_inputs(), Invented(), SyntheticPrivacy()))
        self.assertTrue(report['ranking']['complete'])
        self.assertFalse(report['verification']['final_allowed'])
        display = json.dumps(report['presentation'], ensure_ascii=False)
        self.assertNotIn('99 лет', display)
        self.assertNotIn('ВЫДУМАННАЯ', display)
        self.assertNotIn('национальность', display)
        self.assertIn('Разрабатывал на Python 3 года.', display)
        with tempfile.TemporaryDirectory() as tmp:
            path = write_report(report, Path(tmp))
            csv = (path/'requirements.csv').read_text()
            self.assertNotIn('99 лет', csv)
            self.assertNotIn('национальность', csv)
            self.assertIn('Непроверенное объяснение модели', (path/'report.md').read_text())

    def test_four_statuses_preserve_sources_and_unknown_does_not_assert_inability(self):
        success = asyncio.run(run_pipeline(*demo_inputs(), ReplayModel(), SyntheticPrivacy()))
        disputed = asyncio.run(run_pipeline(*demo_inputs('disputed'), ReplayModel(), SyntheticPrivacy()))
        rows = [r for report in [success, disputed] for j in report['presentation']['jobs'] for r in j['rows']]
        self.assertEqual({r['status'] for r in rows}, {'full','partial','fail','unknown'})
        unknown = next(r for r in rows if r['status']=='unknown')
        self.assertEqual(unknown['resume_quotes'], [])
        self.assertIn('не указаны', unknown['explanation'])
        self.assertTrue(unknown['question'])
        self.assertEqual(success['verification']['requirements'], 'not_reviewed')
        self.assertTrue(all(not j['manager_brief']['final_allowed'] for j in success['presentation']['jobs']))
