"""E9b: evaluation runner against E6. Reports come from the real pipeline with a scripted model whose
statuses are written by hand below, never read from the expectations. Synthetic data only."""
import asyncio
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from evaluation.runner import RunnerError, load_cases, main, run
from prototype.contracts import Fact, Requirement, Requirements, Row
from prototype.demo import SyntheticPrivacy
from prototype.pipeline import run_pipeline

ROOT = Path(__file__).resolve().parents[2]
EXPECTATIONS = ROOT / 'evaluation' / 'expectations' / 'egor' / 'e6-cases.json'
CASES = {c['case_id']: c for c in json.loads(EXPECTATIONS.read_text(encoding='utf-8'))['cases']}

# Vacancy requirements as an extraction model would return them: (id, quote, mandatory_quote)
REQS = {
    'job-fe': [('r1', 'React от 2 лет', 'Обязательно:\n- React от 2 лет'),
               ('r2', 'TypeScript', 'Обязательно:\n- React от 2 лет\n- TypeScript'),
               ('r3', 'Next.js', None)],
    'job-fa': [('r1', 'Опыт учёта основных средств от 3 лет', 'Обязательно:\n- Опыт учёта основных средств от 3 лет'),
               ('r2', '1С:Бухгалтерия', 'Обязательно:\n- Опыт учёта основных средств от 3 лет\n- 1С:Бухгалтерия'),
               ('r3', 'проведение инвентаризации', None)],
    'job-ed': [('r1', 'Высшее образование', 'Обязательно:\n- Высшее образование'),
               ('r2', 'Опыт организации учебного процесса от 1 года',
                'Обязательно:\n- Высшее образование\n- Опыт организации учебного процесса от 1 года'),
               ('r3', 'Работа с LMS (Moodle)', None)],
}
UNKNOWN = [('unknown', [])] * 3

# Hand-written answers: facts and, per vacancy, (status, fact ids) for r1..r3; None = the job fails.
PLANS = {
    'E6-FE-01': {'facts': ['2021–2024 — React и TypeScript, интерфейсы личного кабинета.', 'Next.js в двух проектах.',
                           'Работаю удалённо.'],
                 'jobs': {'job-fe': [('full', ['f1']), ('full', ['f1']), ('full', ['f2'])], 'job-fa': UNKNOWN},
                 'conditions': {'job-fe': [{'kind': 'work_mode', 'state': 'compatible',
                                            'cv': {'fact_id': 'f3', 'quote': 'Работаю удалённо.'},
                                            'vacancy_quote': 'Формат работы: удалённо.', 'note': 'Оба — удалённо.'}]}},
    'E6-FE-02': {'facts': ['С React не работал, прохожу курс.', 'TypeScript изучаю самостоятельно.'],
                 'jobs': {'job-fe': [('fail', ['f1']), ('partial', ['f2']), ('unknown', [])]}},
    'E6-FE-04': {'facts': ['Пишу на React три года, все проекты на TypeScript.'],
                 'jobs': {'job-fe': [('full', ['f1']), ('full', ['f1']), ('unknown', [])]}},
    'E6-FE-05': {'facts': ['Опыт React — 3 года', 'TypeScript использую во всех проектах.'],
                 'jobs': {'job-fe': [('full', ['f1']), ('full', ['f2']), ('unknown', [])]}},
    'E6-FA-02': {'facts': ['Январь 2021 — декабрь 2022: бухгалтер по учёту ОС на заводе.',
                           'Работаю в 1С:Бухгалтерия.'],
                 'jobs': {'job-fa': [('partial', ['f1']), ('full', ['f2']), ('unknown', [])]}},
    'E6-ED-04': {'facts': ['Куратор учебных групп в вузе, 2020–2023.', 'Высшее образование.'],
                 'jobs': {'job-ed': [('full', ['f2']), ('partial', ['f1']), ('unknown', [])], 'job-fe': None}},
}


EMPTY_PROFILE = {'summary': [], 'stack': [], 'last_position': None, 'achievements': [],
                 'missing': ['summary', 'stack', 'last_position', 'achievements']}


class Scripted:
    """Answers in the integrated wire DTOs: the profile with the facts, conditions with the rows."""

    def __init__(self, plan, texts):
        self.plan, self.by_text = plan, {text: job for job, text in texts.items()}

    async def ask(self, schema, task, payload):
        if task == 'facts':
            facts = [Fact(id=f'f{i}', text='факт', quote=q) for i, q in enumerate(self.plan['facts'], 1)]
            return schema.model_validate({'items': [f.model_dump() for f in facts], 'profile': EMPTY_PROFILE})
        if task == 'requirements':
            job = self.by_text[payload['text']]
            if self.plan['jobs'][job] is None:  # a real per-vacancy failure: the quote is not in the vacancy
                missing = Requirement(id='r1', text='x', quote='нет в вакансии', mandatory_quote=None)
                return Requirements(items=[missing])
            return Requirements(items=[Requirement(id=i, text=q, quote=q, mandatory_quote=m) for i, q, m in REQS[job]])
        job = next(j for j, rows in self.plan['jobs'].items() if rows is not None and
                   [r['quote'] for r in payload['requirements']['items']] == [q for _, q, _ in REQS[j]])
        rows = [Row(requirement_id=f'r{i}', status=s, fact_ids=ids, comment='c',
                    question=None if s == 'full' else 'Уточните.').model_dump()
                for i, (s, ids) in enumerate(self.plan['jobs'][job], 1)]
        return schema.model_validate({'rows': rows,
                                      'conditions': {'items': self.plan.get('conditions', {}).get(job, [])}})


def make_report(case_id, plan=None, mode='synthetic_replay'):
    case = CASES[case_id]
    texts = {v['job_id']: v['text'] for v in case['vacancies']}
    report = asyncio.run(run_pipeline(case['cv_text'], list(texts.items()), Scripted(plan or PLANS[case_id], texts),
                                      SyntheticPrivacy()))
    report['mode'] = mode
    return {k: v for k, v in report.items() if k != 'events'}


def evaluate(reports, cases=None, mode='synthetic_replay'):
    cases = cases or [CASES[c] for c in reports]
    return run(cases, mode, reports, {})


def metric(summary, name):
    return next(m for m in summary['metrics'] if m['metric'] == name)


class GoodReportTests(unittest.TestCase):
    def test_handwritten_good_answers_pass_every_measured_check(self):
        summary = evaluate({c: make_report(c) for c in PLANS})
        for m in summary['metrics']:
            with self.subTest(m['metric']):
                self.assertEqual(m['failures'], [])
        self.assertEqual(metric(summary, 'status_allowed')['value'], 1.0)
        self.assertEqual(metric(summary, 'conditions')['value'], 1.0)
        self.assertEqual(metric(summary, 'equivalent_wording_consistent')['value'], 1.0)  # only G-FE is present
        self.assertFalse(summary['quality_measured'])
        self.assertIn('не измерено', summary['note'])

    def test_allowed_alternatives_are_accepted(self):
        plan = copy.deepcopy(PLANS['E6-FA-02'])
        plan['jobs']['job-fa'][0] = ('fail', ['f1'])  # fail and partial are both allowed for overlapping periods
        for p in (PLANS['E6-FA-02'], plan):
            summary = evaluate({'E6-FA-02': make_report('E6-FA-02', p)})
            self.assertEqual(metric(summary, 'row_fully_correct')['failures'], [])
            self.assertEqual(metric(summary, 'recommendation_allowed')['value'], 1.0)

    def test_expected_failure_is_not_applicable_and_incomplete_is_required(self):
        summary = evaluate({'E6-ED-04': make_report('E6-ED-04')})  # job-fe really fails in the pipeline
        self.assertEqual((summary['results'][0]['setup'], summary['row_outcomes']), ('ok', {'pass': 3}))
        self.assertEqual(summary['results'][0]['recommendation'], {'actual': 'incomplete', 'outcome': 'pass'})


class FalsePerfectTests(unittest.TestCase):
    def test_one_forbidden_status_fails(self):
        plan = copy.deepcopy(PLANS['E6-FE-02'])
        plan['jobs']['job-fe'][0] = ('full', ['f1'])  # «С React не работал» as full
        summary = evaluate({'E6-FE-02': make_report('E6-FE-02', plan)})
        self.assertEqual(metric(summary, 'status_allowed')['failures'], ['E6-FE-02'])
        self.assertLess(metric(summary, 'status_allowed')['value'], 1)

    def test_wrong_condition_state_fails(self):
        plan = copy.deepcopy(PLANS['E6-FE-01'])
        plan['conditions']['job-fe'][0]['state'] = 'conflict'
        summary = evaluate({'E6-FE-01': make_report('E6-FE-01', plan)})
        self.assertEqual(metric(summary, 'conditions')['failures'], ['E6-FE-01'])

    def test_swapped_mandatory_pair_fails(self):
        plan = copy.deepcopy(PLANS['E6-FE-01'])
        plan['jobs']['job-fe'] = [('fail', ['f1']), ('full', ['f1']), ('full', ['f2'])]
        summary = evaluate({'E6-FE-01': make_report('E6-FE-01', plan)})
        self.assertEqual(metric(summary, 'rank_relations')['failures'], ['E6-FE-01'])

    def test_tie_does_not_satisfy_a_strict_pair(self):
        plan = copy.deepcopy(PLANS['E6-FE-01'])
        plan['jobs']['job-fe'] = UNKNOWN  # both vacancies at L=0 in the same group: a shared place
        summary = evaluate({'E6-FE-01': make_report('E6-FE-01', plan)})
        self.assertEqual(metric(summary, 'rank_relations')['failures'], ['E6-FE-01'])

    def test_missing_case_is_not_perfect(self):
        cases = [CASES['E6-FE-01'], CASES['E6-FE-02']]
        summary = run(cases, 'synthetic_replay', {'E6-FE-01': make_report('E6-FE-01')}, {})
        evaluated = metric(summary, 'cases_evaluated')
        self.assertEqual((evaluated['numerator'], evaluated['denominator']), (1, 2))

    def test_missing_case_stays_unmeasured_in_every_check(self):
        cases = [CASES['E6-FE-01'], CASES['E6-FE-02']]  # FE-01 has a rank pair; its report is missing
        summary = run(cases, 'synthetic_replay', {'E6-FE-02': make_report('E6-FE-02')}, {})
        for name in ('status_allowed', 'row_fully_correct', 'rank_relations', 'recommendation_allowed',
                     'references_valid', 'requirement_extraction_coverage', 'conditions'):
            with self.subTest(name):
                self.assertIn('E6-FE-01:missing_report', metric(summary, name)['unmeasured'])
        self.assertIsNone(metric(summary, 'rank_relations')['value'])  # never 100% on nothing

    def test_whole_cv_fact_is_not_matching_evidence(self):
        plan = copy.deepcopy(PLANS['E6-FE-01'])
        plan['facts'] = [CASES['E6-FE-01']['cv_text']]  # one fact quoting the whole resume
        plan['jobs']['job-fe'] = [('full', ['f1'])] * 3
        plan.pop('conditions')
        summary = evaluate({'E6-FE-01': make_report('E6-FE-01', plan)})
        self.assertEqual(metric(summary, 'evidence_matches_expected_quote')['failures'], ['E6-FE-01'])

    def test_malformed_report_is_a_setup_error_not_a_traceback(self):
        base = make_report('E6-FE-04')
        broken = [copy.deepcopy(base) for _ in range(3)]
        del broken[0]['ranking']['jobs'][0]['evaluation']
        broken[1]['ranking']['jobs'][0]['evaluation']['rows'][0].pop('status')
        broken[2]['ranking']['jobs'][0]['evidence_check']['rows'][0]['state'] = 'nonsense'
        for report in broken:
            with self.subTest():
                summary = evaluate({'E6-FE-04': report})
                self.assertEqual(summary['results'][0]['setup'], 'malformed_report')
                self.assertIsNone(metric(summary, 'status_allowed')['value'])

    def test_single_member_group_is_unmeasured(self):
        summary = evaluate({'E6-FE-04': make_report('E6-FE-04')})
        self.assertIsNone(metric(summary, 'equivalent_wording_consistent')['value'])

    def test_empty_actual_is_not_perfect(self):
        empty = make_report('E6-FE-04')
        empty['ranking']['jobs'] = []
        summary = evaluate({'E6-FE-04': empty})
        self.assertEqual(summary['results'][0]['setup'], 'job_set_mismatch')
        self.assertIsNone(metric(summary, 'status_allowed')['value'])

    def test_wrong_reference_fails(self):
        report = make_report('E6-FE-04')
        report['facts']['items'][0]['quote'] = 'Пишу на Rust десять лет.'
        summary = evaluate({'E6-FE-04': report})
        self.assertEqual(metric(summary, 'references_valid')['failures'], ['E6-FE-04'])

    def test_unrelated_evidence_is_wrong_evidence(self):
        plan = copy.deepcopy(PLANS['E6-FE-01'])
        plan['jobs']['job-fe'][2] = ('full', ['f1'])  # Next.js «proved» by the React sentence
        summary = evaluate({'E6-FE-01': make_report('E6-FE-01', plan)})
        self.assertEqual(summary['row_outcomes'].get('wrong_evidence'), 1)
        self.assertEqual(metric(summary, 'evidence_matches_expected_quote')['failures'], ['E6-FE-01'])

    def test_wrong_mandatory_marking_fails(self):
        report = make_report('E6-FE-04')
        report['ranking']['jobs'][0]['requirements']['items'][2]['mandatory_quote'] = 'Желательно:\n- Next.js'
        summary = evaluate({'E6-FE-04': report})
        self.assertEqual(metric(summary, 'mandatory_marking')['failures'], ['E6-FE-04'])

    def test_unreproduced_failure_is_a_setup_error(self):
        plan = copy.deepcopy(PLANS['E6-ED-04'])
        plan['jobs']['job-fe'] = UNKNOWN  # job-fe processed although the case expects it to fail
        summary = evaluate({'E6-ED-04': make_report('E6-ED-04', plan)})
        self.assertEqual(summary['results'][0]['setup'], 'expected_failure_not_reproduced')

    def test_unexpected_job_failure_is_an_error_not_unknown(self):
        plan = copy.deepcopy(PLANS['E6-FE-01'])
        plan['jobs']['job-fa'] = None
        summary = evaluate({'E6-FE-01': make_report('E6-FE-01', plan)})
        self.assertEqual(summary['row_outcomes'].get('error'), 3)
        self.assertEqual(metric(summary, 'rows_without_processing_error')['failures'], ['E6-FE-01'])

    def test_inconsistent_equivalent_wordings_fail(self):
        plan = copy.deepcopy(PLANS['E6-FE-05'])
        plan['jobs']['job-fe'][1] = ('partial', ['f2'])
        summary = evaluate({'E6-FE-04': make_report('E6-FE-04'), 'E6-FE-05': make_report('E6-FE-05', plan)})
        self.assertEqual(metric(summary, 'equivalent_wording_consistent')['failures'], ['G-FE'])

    def test_expectations_file_is_not_a_report(self):
        expectations = json.loads(EXPECTATIONS.read_text(encoding='utf-8'))
        summary = evaluate({'E6-FE-01': expectations})
        self.assertEqual(summary['results'][0]['setup'], 'unknown_report_version')


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)

    def write(self, mode, reports):
        (self.dir / 'r').mkdir(exist_ok=True)
        for case_id, report in reports.items():
            (self.dir / 'r' / f'{case_id}.json').write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
        manifest = {'mode': mode, 'reports': {c: f'{c}.json' for c in reports}}
        (self.dir / 'r' / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')

    def cli(self, split='dev', expectations=EXPECTATIONS):
        return main(['--reports', str(self.dir / 'r'), '--expectations', str(expectations), '--split', split,
                     '--out', str(self.dir / 'out')])

    def test_command_writes_json_and_markdown(self):
        self.write('synthetic_replay', {'E6-FE-01': make_report('E6-FE-01')})
        self.assertEqual(self.cli(), 0)
        data = json.loads((self.dir / 'out' / 'evaluation.json').read_text(encoding='utf-8'))
        self.assertEqual(metric(data, 'cases_evaluated')['numerator'], 1)
        self.assertIn('не измерено', (self.dir / 'out' / 'evaluation.md').read_text(encoding='utf-8'))

    def test_mixed_modes_are_refused(self):
        self.write('synthetic_replay', {'E6-FE-01': make_report('E6-FE-01', mode='live')})
        self.assertEqual(self.cli(), 2)

    def test_a_report_without_its_own_mode_is_refused(self):
        report = make_report('E6-FE-01')
        del report['mode']
        self.write('live', {'E6-FE-01': report})
        self.assertEqual(self.cli(), 2)

    def test_cli_mode_names_are_mapped(self):
        report = make_report('E6-FE-01', mode='synthetic_replay_NOT_model_output')  # what `prototype demo` writes
        self.write('synthetic_replay', {'E6-FE-01': report})
        self.assertEqual(self.cli(), 0)
        self.write('live', {'E6-FE-01': report})
        self.assertEqual(self.cli(), 2)
        self.write('live', {'E6-FE-01': make_report('E6-FE-01', mode='live_local_privacy')})
        self.assertEqual(self.cli(), 0)
        data = json.loads((self.dir / 'out' / 'evaluation.json').read_text(encoding='utf-8'))
        self.assertTrue(data['quality_measured'])

    def test_bad_manifests_are_refused(self):
        self.write('synthetic_replay', {'E6-FE-01': make_report('E6-FE-01')})
        manifest = self.dir / 'r' / 'manifest.json'
        for text in ('{"mode": "synthetic_replay", "reports": ["E6-FE-01.json"]}',
                     '{"mode": "synthetic_replay", "reports": {"E6-FE-01": "E6-FE-01.json", '
                     '"E6-FE-02": "E6-FE-01.json"}}',
                     '{"mode": "synthetic_replay", "reports": {"E6-FE-01": "a.json", "E6-FE-01": "b.json"}}',
                     '[]'):
            with self.subTest(text):
                manifest.write_text(text, encoding='utf-8')
                self.assertEqual(self.cli(), 2)

    def test_non_object_report_is_not_measured(self):
        self.write('synthetic_replay', {})
        (self.dir / 'r' / 'E6-FE-01.json').write_text('[]', encoding='utf-8')
        (self.dir / 'r' / 'manifest.json').write_text(
            json.dumps({'mode': 'synthetic_replay', 'reports': {'E6-FE-01': 'E6-FE-01.json'}}), encoding='utf-8')
        self.assertEqual(self.cli(), 0)
        data = json.loads((self.dir / 'out' / 'evaluation.json').read_text(encoding='utf-8'))
        result = next(r for r in data['results'] if r['case_id'] == 'E6-FE-01')
        self.assertEqual(result['setup'], 'malformed_report')

    def test_holdout_needs_its_digest(self):
        self.write('synthetic_replay', {})
        self.assertEqual(self.cli('holdout'), 0)
        broken = self.dir / 'e'
        broken.mkdir()
        data = json.loads(EXPECTATIONS.read_text(encoding='utf-8'))
        next(c for c in data['cases'] if c['split'] == 'holdout')['requirements'][0]['allowed_status'].append('full')
        (broken / 'e6-cases.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        shutil.copy(EXPECTATIONS.parent / 'holdout.sha256', broken / 'holdout.sha256')
        self.assertEqual(self.cli('holdout', broken / 'e6-cases.json'), 2)
        with self.assertRaises(RunnerError):
            load_cases(broken / 'e6-cases.json', 'holdout')
        (broken / 'holdout.sha256').write_text('', encoding='utf-8')
        self.assertEqual(self.cli('holdout', broken / 'e6-cases.json'), 2)

    def test_report_outside_the_directory_is_refused(self):
        self.write('synthetic_replay', {})
        (self.dir / 'r' / 'manifest.json').write_text(
            json.dumps({'mode': 'synthetic_replay', 'reports': {'E6-FE-01': '../secret.json'}}), encoding='utf-8')
        self.assertEqual(self.cli(), 2)


if __name__ == '__main__':
    unittest.main()
