"""Run both real CLI replays and validate their artifacts. No API keys or live mode."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


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
            report = json.loads(path.read_text())
            assert report['mode'] == 'synthetic_replay_NOT_model_output', 'explicit_replay_mode'
            assert report['ranking']['complete'] is True, 'complete_replay'
            assert report['ranking']['recommendation'] == recommendation, 'scenario_recommendation'
            jobs = report['ranking']['jobs']
            assert len(jobs) == 3 and not report['errors'], 'three_successful_jobs'
            assert report['profile']['state'] == 'structure_ok', 'sourced_profile'
            assert (path.parent / 'report.md').stat().st_size > 0, 'markdown_artifact'
            for job in jobs:
                statuses.update(row['status'] for row in job['evaluation']['rows'])
                assert 'comparisons' in report and 'handoff' in report, 'derived_report_artifacts'
            if with_ui:
                subprocess.run(['node', '-e',
                    "const fs=require('fs'); const ui=require('./prototype/static/report.js'); "
                    "ui.parseReport(fs.readFileSync(process.argv[1],'utf8'));",
                    str(path)], cwd=ROOT, check=True, capture_output=True)
            summaries.append({'scenario': scenario, 'jobs': len(jobs), 'recommendation': recommendation})
    assert statuses == {'full', 'partial', 'fail', 'unknown'}, 'four_statuses_across_replays'
    return {'status': 'pass', 'mode': 'synthetic_replay_NOT_model_output',
            'quality_measured': False, 'ui_parser_checked': with_ui, 'scenarios': summaries}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--without-ui', action='store_true', help='Python-only Docker image has no Node runtime')
    args = parser.parse_args()
    try:
        result = check(with_ui=not args.without_ui)
    except Exception as exc:
        # Inputs are built-in synthetic data, nevertheless do not echo subprocess output.
        print(json.dumps({'status': 'failed', 'code': type(exc).__name__}))
        raise SystemExit(1)
    print(json.dumps(result))
