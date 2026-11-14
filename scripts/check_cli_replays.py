"""Run both real CLI replays and validate their artifacts. No API keys or live mode."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REPORT_FILES = {'report.json', 'report.md', 'requirements.csv'}
CSV_COLUMNS = ['job_id', 'requirement_id', 'requirement', 'job_quote', 'mandatory_quote',
               'status', 'resume_evidence', 'comment', 'question', 'verification']


def check_csv(path, report):
    facts = {f['id']: f['quote'] for f in report['facts']['items']}
    expected = {}
    for job in report['ranking']['jobs']:
        requirements = {r['id']: r['quote'] for r in job['requirements']['items']}
        for row in job['evaluation']['rows']:
            rid = row['requirement_id']
            expected[job['job_id'], rid] = (row['status'], requirements[rid],
                                           ' / '.join(facts[f] for f in row['fact_ids']))
    seen = set()
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == CSV_COLUMNS, 'csv_columns'
        for row in reader:
            key = (row['job_id'], row['requirement_id'])
            assert None not in row and key in expected and key not in seen, 'csv_row_key'
            assert row['verification'] == 'model_proposed_not_verified', 'csv_verification'
            assert (row['status'], row['job_quote'], row['resume_evidence']) == expected[key], 'csv_evidence'
            seen.add(key)
    assert seen == expected.keys(), 'csv_row_coverage'


def check(with_ui=True):
    summaries = []
    statuses = set()
    with tempfile.TemporaryDirectory(prefix='recruiter-cli-check-') as temporary:
        for scenario, recommendation in [('success', 'review_top'), ('disputed', 'clarify')]:
            output = Path(temporary) / scenario
            subprocess.run([sys.executable, '-m', 'prototype', 'demo', '--scenario', scenario,
                            '--out', str(output)], cwd=ROOT, check=True, capture_output=True)
            reports = list(output.rglob('report.json'))
            assert len(reports) == 1, 'one_report_per_cli_run'
            path = reports[0]
            assert {item.name for item in path.parent.iterdir()} == REPORT_FILES, 'report_export_files'
            report = json.loads(path.read_text())
            assert report['mode'] == 'synthetic_replay_NOT_model_output', 'explicit_replay_mode'
            assert report['ranking']['complete'] is True, 'complete_replay'
            assert report['ranking']['recommendation'] == recommendation, 'scenario_recommendation'
            jobs = report['ranking']['jobs']
            assert len(jobs) == 3 and not report['errors'], 'three_successful_jobs'
            assert report['profile']['state'] == 'structure_ok', 'sourced_profile'
            assert report['verification']['final_allowed'] is False, 'draft_report'
            markdown = (path.parent / 'report.md').read_text(encoding='utf-8')
            assert all(value in markdown for value in (report['mode'], recommendation, '3/3')), 'markdown_artifact'
            check_csv(path.parent / 'requirements.csv', report)
            for job in jobs:
                statuses.update(row['status'] for row in job['evaluation']['rows'])
                assert 'comparisons' in report and 'handoff' in report, 'derived_report_artifacts'
            if report.get('policy_version') == 'draft-2026-11-14-v3':
                assert report['leader'] and report['leader']['state'] == report['ranking']['leader']['state'], 'leader_explanation_connected'
            if with_ui:
                subprocess.run(['node', '-e',
                    "const fs=require('fs'); const ui=require('./prototype/static/report.js'); "
                    "const raw=fs.readFileSync(process.argv[1],'utf8'); const parsed=ui.parseReport(raw); "
                    "if(JSON.parse(raw).leader && !parsed.leader) throw new Error('leader_projection_lost');",
                    str(path)], cwd=ROOT, check=True, capture_output=True)
            summaries.append({'scenario': scenario, 'jobs': len(jobs), 'recommendation': recommendation})
    assert statuses == {'full', 'partial', 'fail', 'unknown'}, 'four_statuses_across_replays'
    return {'status': 'pass', 'mode': 'synthetic_replay_NOT_model_output',
            'quality_measured': False, 'ui_parser_checked': with_ui, 'export_files': sorted(REPORT_FILES),
            'scenarios': summaries}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--without-ui', action='store_true', help='Python-only Docker image has no Node runtime')
    args = parser.parse_args()
    try:
        result = check(with_ui=not args.without_ui)
    except Exception as exc:
        # Inputs are built-in synthetic data, nevertheless do not echo subprocess output.
        code = str(exc) if type(exc) is AssertionError else type(exc).__name__
        print(json.dumps({'status': 'failed', 'code': code}))
        raise SystemExit(1)
    print(json.dumps(result))
