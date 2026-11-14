import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from evaluation import saved_reports as review
from evaluation.example_reports import example_report
from prototype.documents import read_document
from prototype.evidence import Source, locate, sha256_text


def sample_case():
    quote = 'React от 2 лет'
    return {
        'case_id': 'E6-TEST', 'split': 'dev', 'domain': 'frontend', 'decision_status': 'draft',
        'equivalence_group': None, 'cv_text': 'React использую три года.\nВерстал интерфейсы на HTML.',
        'vacancies': [{'job_id': 'job-fe', 'text': f'Обязательно:\n- {quote}\nЖелательно: TypeScript.'}],
        'unprocessed_job_ids': [],
        'requirements': [
            {'job_id': 'job-fe', 'key': 'react', 'quote': quote, 'mandatory': True,
             'allowed_status': ['full'], 'cv_quotes': ['React использую три года.']},
            {'job_id': 'job-fe', 'key': 'ts', 'quote': 'TypeScript', 'mandatory': False,
             'allowed_status': ['unknown'], 'cv_quotes': []},
        ],
        'ranking': {'relations': [], 'allowed_recommendations': ['review_top']},
        'conditions': [], 'forbidden_conclusions': ['Проверить произвольный вывод вручную'],
    }


class SavedReportTests(unittest.TestCase):
    def setUp(self):
        self.case = sample_case()
        self.report = example_report(self.case)

    def outcomes(self, report=None, case=None):
        result = review.check_case(case or self.case, self.report if report is None else report, 'replay')
        return [row['outcome'] for row in result['rows']], result

    def test_reference_passes_and_wrong_but_real_citation_fails(self):
        self.assertEqual(self.outcomes()[0], ['pass', 'pass'])
        wrong = example_report(self.case, wrong_evidence_key='react')
        self.assertEqual(self.outcomes(wrong)[0], ['wrong_evidence', 'pass'])

    def test_missing_and_unexpected_processing_error_are_distinct(self):
        empty = review.not_run(self.case)
        self.assertEqual([row['outcome'] for row in empty['rows']], ['not_run', 'not_run'])
        failed = self.report
        failed['ranking']['jobs'] = []
        failed['ranking']['complete'] = False
        failed['ranking']['recommendation'] = 'incomplete'
        failed['errors'] = [{'job_id': 'job-fe', 'code': 'model_invalid'}]
        failed['unprocessed_job_ids'] = ['job-fe']
        failed['unprocessed'] = [{'job_id': 'job-fe', 'reason': 'model_invalid'}]
        failed['presentation']['jobs'] = []
        self.assertEqual(self.outcomes(failed)[0], ['error', 'error'])

    def test_expected_unprocessed_vacancy_needs_a_recorded_error(self):
        case = copy.deepcopy(self.case)
        case['vacancies'].append({'job_id': 'job-fa', 'text': 'Вакансия бухгалтера.'})
        case['unprocessed_job_ids'] = ['job-fa']
        case['ranking']['allowed_recommendations'] = ['incomplete']
        report = example_report(case)
        outcomes, result = self.outcomes(report, case)
        self.assertEqual(outcomes, ['pass', 'pass'])
        self.assertEqual(result['recommendation'], 'pass')
        report['errors'] = []
        self.assertIn('setup_error', self.outcomes(report, case)[1]['issues'])
        report = example_report(case)
        del report['unprocessed']
        self.assertIn('setup_error', self.outcomes(report, case)[1]['issues'])
        report = example_report(case)
        report['unprocessed'][0]['reason'] = 'unrelated'
        self.assertEqual(self.outcomes(report, case)[1]['status'], 'failed')

    def test_a_wider_quote_can_match_only_one_expected_requirement(self):
        requirements = self.case['requirements']
        jobs = self.case['vacancies']
        actual = {'id': 'x', 'quote': 'React от 2 лет\nЖелательно: TypeScript.'}
        matched = review.match_requirements(jobs[0]['text'], requirements, [actual])
        self.assertEqual(matched, {'react': 'x'})

    def test_unknown_is_not_fail_and_unbound_id_is_an_error(self):
        job = self.report['ranking']['jobs'][0]
        row = job['evaluation']['rows'][1]
        row.update(status='fail', fact_ids=[self.report['facts']['items'][0]['id']])
        self.report.pop('presentation')
        job.pop('evidence_check')
        self.assertEqual(self.outcomes()[0][1], 'wrong_status')
        row['requirement_id'] = 'unbound'
        self.assertEqual(self.outcomes()[0], ['error', 'error'])

    def test_tampered_projection_and_replay_never_count_as_live_quality(self):
        self.report['presentation']['jobs'][0]['manager_brief']['final_allowed'] = True
        outcomes, result = self.outcomes()
        self.assertEqual(outcomes, ['pass', 'pass'])
        self.assertIn('invalid_presentation', result['issues'])
        self.assertIn('mode_mismatch', review.check_case(self.case, self.report, 'live')['issues'])

    def test_source_derived_job_ids_work_and_invented_projection_fails(self):
        job, = self.report['ranking']['jobs']
        original_id = job['job_id']
        jid = 'job-' + sha256_text(self.case['vacancies'][0]['text'])[:24] + '-1'
        job['job_id'] = jid
        job['evidence_check']['vacancy_id'] = jid
        job['requirements_draft']['vacancy_id'] = jid
        job['requirements_review']['vacancy_id'] = jid
        shown, = self.report['presentation']['jobs']
        self.assertEqual(shown['job_id'], original_id)
        shown['job_id'] = jid
        self.assertEqual(self.outcomes()[1]['status'], 'checked')
        shown['rows'][0]['explanation'] = 'Придуманное утверждение о кандидате'
        self.assertIn('invalid_presentation', self.outcomes()[1]['issues'])

    def test_equivalence_detects_different_statuses_even_with_another_failure(self):
        first, second = [dict(self.case, case_id='E6-' + name, equivalence_group='G') for name in ('A', 'B')]
        a = review.check_case(first, self.report, 'replay')
        b = copy.deepcopy(a)
        b['case_id'] = second['case_id']
        b['rows'][0]['status'] = 'partial'
        b['status'] = 'failed'
        b['rows'][1].pop('status')
        outcomes = review.check_groups([first, second], [a, b])
        self.assertEqual({row['key']: row['outcome'] for row in outcomes}, {'react': 'fail', 'ts': 'not_run'})

    def test_fabricated_fact_fails_its_row_and_a_punctuation_only_overlap_is_insufficient(self):
        self.report['facts']['items'][0]['quote'] = 'Такой цитаты в резюме нет.'
        self.report.pop('presentation')
        self.report['ranking']['jobs'][0].pop('evidence_check')
        self.assertEqual(self.outcomes()[0], ['wrong_evidence', 'pass'])
        report = example_report(self.case)
        report['facts']['items'][0]['quote'] = '.\nВерстал интерфейсы на HTML.'
        report.pop('presentation')
        report['ranking']['jobs'][0].pop('evidence_check')
        self.assertEqual(self.outcomes(report)[0], ['wrong_evidence', 'pass'])

    def test_global_error_and_fabricated_requirements_draft_cannot_pass(self):
        self.report['errors'].append({'job_id': None, 'code': 'model_invalid', 'stage': 'facts'})
        self.assertEqual(self.outcomes()[1]['status'], 'failed')
        report = example_report(self.case)
        report['ranking']['jobs'][0]['requirements_draft']['vacancy_id'] = 'job-invented'
        self.assertEqual(self.outcomes(report)[1]['status'], 'failed')

    def test_profile_display_must_be_supported_by_its_own_spans(self):
        source = Source.of('cv', self.case['cv_text'])
        quote = self.case['requirements'][0]['cv_quotes'][0]
        profile = self.report['profile']
        profile['spans']['summary[0]'] = [locate(source, quote).span.model_dump()]
        profile['display']['summary[0]'] = quote
        self.assertEqual(self.outcomes()[1]['status'], 'checked')
        profile['display']['summary[0]'] = 'React использую 15 лет.'
        self.assertIn('invalid_profile', self.outcomes()[1]['issues'])

    def test_condition_rejects_a_stale_source_span(self):
        case = next(case for case in review.load_expectations(review.DEFAULT_EXPECTATIONS)
                    if case['case_id'] == 'E6-FA-04')
        report = example_report(case)
        self.assertEqual(self.outcomes(report, case)[1]['status'], 'checked')
        job = next(job for job in report['ranking']['jobs'] if job['job_id'] == 'job-fa')
        job['conditions']['items'][0]['vacancy_span']['start'] += 1
        outcomes = self.outcomes(report, case)[1]['conditions']
        self.assertEqual([item['outcome'] for item in outcomes], ['fail', 'pass'])

    def test_synthetic_docx_and_pdf_match_their_text_hashes(self):
        folder = Path(__file__).resolve().parents[1] / 'fixtures' / 'documents'
        documents = json.loads((folder / 'manifest.json').read_text())['documents']
        self.assertEqual(len(documents), 9)
        for doc in documents:
            with self.subTest(file=doc['file']):
                self.assertEqual(sha256_text(read_document(folder / doc['file'])), doc['text_sha256'])

    def test_cli_rejects_bad_report_and_preserves_separate_counts(self):
        second = dict(self.case, case_id='E6-MISSING')
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            reports = folder / 'reports'
            reports.mkdir()
            output = folder / 'summary'
            cases = folder / 'expectations.json'
            cases.write_text(json.dumps({'schema_version': review.SCHEMA, 'cases': [self.case, second]}))
            wrong = example_report(self.case, wrong_evidence_key='react')
            (reports / 'E6-TEST.json').write_text(json.dumps(wrong))
            self.assertEqual(review.main(['--expectations', str(cases), '--reports', str(reports),
                                          '--out', str(output)]), 1)
            data = json.loads((output / 'summary.json').read_text())
            self.assertEqual(data['overall']['rows']['wrong_evidence'], 1)
            self.assertEqual(data['overall']['rows']['not_run'], 2)
            self.assertEqual(data['model_quality'], 'not_measured')
            self.assertTrue((output / 'summary.md').is_file())
