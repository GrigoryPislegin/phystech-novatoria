"""Synthetic policy cases cross the Python report / JS viewer boundary without model calls."""
import csv
import json
import tempfile
from pathlib import Path
import shutil
import subprocess
import unittest

from prototype.pipeline import refresh_derived, write_report
from prototype.scoring import POLICY_VERSION
from prototype.tests.test_scoring_v3 import report_of


@unittest.skipUnless(shutil.which('node'), 'Node required for the report/UI contract check')
class ScoringUIIntegrationTests(unittest.TestCase):
    def test_repeat_units_keep_source_backed_explanations_and_review_flags(self):
        for statuses in [('full', 'full'), ('unknown', 'full'), ('full', 'fail')]:
            with self.subTest(statuses=statuses):
                report = report_of({'jobs': [{'job_id': 'j', 'rows': [
                    {'id': f'r{i}', 'text': 'Python', 'quote': 'Python', 'status': status, 'm': False}
                    for i, status in enumerate(statuses)]}]})
                report.update(schema_version='0.1', policy_version=POLICY_VERSION,
                              mode='synthetic_policy_fixture_NOT_model_output',
                              unprocessed_job_ids=[], unprocessed=[], errors=[])
                refresh_derived(report)
                if report['ranking']['jobs'][0]['score']['conflict_ids']:
                    brief = report['presentation']['jobs'][0]['manager_brief']
                    self.assertEqual(brief['grounds'], [])
                    self.assertEqual(len(brief['risks']), 2)
                    self.assertEqual(brief['questions'], [])
                    with tempfile.TemporaryDirectory() as directory:
                        out = write_report(report, Path(directory))
                        markdown = (out/'report.md').read_text()
                        self.assertIn('Конфликт повторов', markdown)
                        self.assertNotIn('Вопрос для уточнения:', markdown)
                        with (out/'requirements.csv').open() as handle:
                            exported = list(csv.DictReader(handle))
                        self.assertEqual([row['status'] for row in exported], ['full', 'fail'])
                        self.assertTrue(all(row['verification'] == 'conflicting_repeat_requires_review'
                                            and not row['question'] for row in exported))
                check = subprocess.run(['node', '-e', """
                    const fs=require('fs'), assert=require('node:assert/strict');
                    const {parseReport,describeFit}=require('./prototype/static/report.js');
                    const raw=JSON.parse(fs.readFileSync(0,'utf8'));
                    const view=parseReport(JSON.stringify(raw));
                    assert.ok(view.leader, 'actual backend explanation must remain visible');
                    const conflict=raw.ranking.jobs[0].score.conflict_ids.length>0;
                    if (conflict) {
                        assert.equal(view.leader.factors.length,0);
                        assert.equal(describeFit(view,view.jobs[0]).grounds.length,0);
                        assert.equal(describeFit(view,view.jobs[0]).risks.length,2);
                        const html=require('./prototype/static/manager-report.js').renderManagerReport(view,'j');
                        assert.match(html,/Оценки одного требования противоречат/);
                        assert.equal(view.leader.canChange.length,1);
                        assert.equal(view.leader.canChange[0].kind,'disputed');
                        assert.equal(view.reviewItems.filter(item=>item.decisive).length,2);
                    } else {
                        assert.equal(view.leader.factors.length,1);
                        assert.equal(view.leader.factors[0].row.status,'full');
                        assert.equal(view.leader.factors[0].effect,100);
                    }
                    assert.equal(view.finalAllowed,false);
                """], input=json.dumps(report), text=True, capture_output=True,
                    cwd=Path(__file__).resolve().parents[2], timeout=10)
                self.assertEqual(check.returncode, 0, check.stderr)
