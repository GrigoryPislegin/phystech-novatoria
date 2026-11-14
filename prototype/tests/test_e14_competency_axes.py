"""E14: data for the compact summary and the skills radar. Pure arithmetic over a v3 score; synthetic."""
import unittest

from prototype.ranking_explanation import AXES, competency_axes
from prototype.scoring import POLICY_V2, score
from prototype.tests.test_e13_support import load_fixture, run
from prototype.tests.test_e14_evidence_fidelity import one_of_eight

# an-1 «Продуктовый аналитик» of the analytics set: r1…r9 (a handwritten proposal, like the statuses)
LABELS = {'r1': 'relevant_experience', 'r2': 'stack', 'r3': 'relevant_experience', 'r4': 'stack', 'r5': 'stack',
          'r6': 'stack', 'r7': 'domain', 'r8': 'language', 'r9': 'management'}


class AxesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report, _ = run(load_fixture('analytics'))
        cls.jobs = {j['job_id']: j for j in report['ranking']['jobs']}
        cls.facts = {f['id'] for f in report['facts']['items']}

    def test_radar_of_a_vacancy_with_enough_data(self):
        job = self.jobs['an-1']
        result = competency_axes(job, LABELS)
        self.assertEqual((result.radar_ready, result.reason), (True, None))
        self.assertTrue(4 <= len(result.axes) <= 6)
        self.assertEqual([a.axis for a in result.axes], [n for n in AXES if n in set(LABELS.values())])
        self.assertAlmostEqual(sum(a.weight for a in result.axes) + result.outside_weight, 100, places=2)
        ids = [rid for a in result.axes for rid in a.requirement_ids]
        self.assertEqual(sorted(ids), sorted(LABELS))  # every requirement on exactly one axis
        for axis in result.axes:
            self.assertLessEqual(set(axis.fact_ids), self.facts)
            self.assertTrue(0 <= axis.coverage <= 100 and (axis.score is None or 0 <= axis.score <= axis.upper <= 100))
        # The total is the policy's own lower bound: the axes are another view of it, not another formula.
        total = sum(a.weight * a.coverage / 100 * a.score / 100 for a in result.axes if a.score is not None)
        self.assertAlmostEqual(total, job['score']['lower'], places=1)

    def test_axis_weight_follows_the_policy_groups(self):
        result = competency_axes(self.jobs['an-1'], LABELS)
        weights = {a.axis: a.weight for a in result.axes}
        # Five mandatory units share 75 points, four optional ones 25: r1 and r3 are mandatory.
        self.assertEqual(weights['relevant_experience'], 30)
        self.assertEqual(weights['domain'], 6.25)  # one optional unit; a confirmed fail, so its score is 0
        domain = next(a for a in result.axes if a.axis == 'domain')
        self.assertEqual((domain.score, domain.coverage, domain.stop_factor), (0, 100, False))

    def test_too_few_axes_gives_a_short_summary_instead_of_points(self):
        labels = {rid: ('stack' if i % 2 else 'relevant_experience') for i, rid in enumerate(LABELS)}
        result = competency_axes(self.jobs['an-1'], labels)
        self.assertEqual((result.radar_ready, result.reason, len(result.axes)), (False, 'too_few_axes', 2))
        self.assertIn('для диаграммы нужно не меньше 4', result.summary)

    def test_no_labels_or_no_data_never_invents_an_axis(self):
        result = competency_axes(self.jobs['an-1'], None)
        self.assertEqual((result.radar_ready, result.reason, result.axes, result.outside_weight),
                         (False, 'no_labels', [], 100))
        self.assertIn('Подтверждено', result.summary)
        # One counted requirement among eight: four axes exist, data on one only.
        s, _, (reqs, evaluation, evidence) = one_of_eight('Навыки: Vue.js, TypeScript, Git.', 'Опыт работы с Vue.js.',
                                                          'Vue.js')
        job = {'job_id': 'j', 'score': s, 'evaluation': evaluation.model_dump()}
        axes = ['stack', 'relevant_experience', 'domain', 'education']
        result = competency_axes(job, {f'r{i}': axes[i % 4] for i in range(1, 9)})
        self.assertEqual((result.radar_ready, result.reason, len(result.axes)), (False, 'too_little_data', 4))
        empty = [a for a in result.axes if a.coverage == 0]
        self.assertTrue(empty and all(a.score is None for a in empty))  # no point is drawn without evidence
        self.assertEqual(competency_axes({**job, 'score': score(reqs, evaluation, evidence, policy=POLICY_V2)}, None),
                         None)  # an older policy has no units: the view is not offered

    def test_stop_factor_and_disputed_rows(self):
        job = self.jobs['an-2']  # two confirmed fails of mandatory requirements
        labels = {rid: 'stack' for rid in (r['requirement_id'] for r in job['evaluation']['rows'])}
        result = competency_axes(job, labels)
        self.assertTrue(result.axes[0].stop_factor)
        self.assertIn('несоответствие обязательному требованию', result.summary)
        s, _, (_, evaluation, _) = one_of_eight('С Vue.js не работал, писал на jQuery.', 'Опыт работы с Vue.js.',
                                                'Vue.js')
        result = competency_axes({'job_id': 'j', 'score': s, 'evaluation': evaluation.model_dump()}, {'r1': 'stack'})
        self.assertEqual((result.axes[0].score, result.axes[0].coverage, result.axes[0].upper), (None, 0, 100))

    def test_labels_must_name_existing_requirements_and_known_axes(self):
        for labels, code in (({'r99': 'stack'}, 'unknown_requirement_id'), ({'r1': 'charisma'}, 'unknown_axis')):
            with self.assertRaisesRegex(ValueError, code):
                competency_axes(self.jobs['an-1'], labels)
        outside = competency_axes(self.jobs['an-1'], {**LABELS, 'r8': 'other', 'r9': 'conditions'})
        self.assertEqual(outside.outside_weight, 12.5)
        self.assertNotIn('language', [a.axis for a in outside.axes])


class RepeatedUnitLabelTests(unittest.TestCase):
    """A literal repeat is one unit of weight; its rows must name one axis or none."""

    def job(self):
        from evaluation.policy_compare import build_job
        reqs, evaluation, evidence = build_job({'job_id': 'j', 'rows': [
            {'id': 'r1', 'text': 'Python', 'quote': 'Python', 'm': False, 'status': 'full'},
            {'id': 'r2', 'text': 'python', 'quote': 'python.', 'm': False, 'status': 'full'},
            {'id': 'r3', 'text': 'SQL', 'm': False, 'status': 'full'}]})
        s = score(reqs, evaluation, evidence)
        self.assertEqual(s['repeated_ids'], [['r1', 'r2']])
        return {'job_id': 'j', 'score': s, 'evaluation': evaluation.model_dump()}

    def weights(self, labels):
        result = competency_axes(self.job(), labels)
        return {a.axis: a.weight for a in result.axes}, result.outside_weight

    def test_agreeing_rows_put_the_unit_on_their_axis(self):
        self.assertEqual(self.weights({'r1': 'stack', 'r2': 'stack', 'r3': 'stack'}), ({'stack': 100}, 0))

    def test_conflicting_or_missing_labels_leave_the_whole_unit_outside(self):
        for labels in ({'r1': 'management', 'r2': 'stack', 'r3': 'stack'},   # two different axes
                       {'r1': 'stack', 'r3': 'stack'},                       # one row not labelled
                       {'r1': 'stack', 'r2': 'other', 'r3': 'stack'},        # an axis and «other»
                       {'r2': 'stack', 'r1': 'conditions', 'r3': 'stack'}):
            with self.subTest(labels):
                self.assertEqual(self.weights(labels), ({'stack': 50}, 50))

    def test_the_order_of_ids_does_not_choose_the_axis(self):
        first = self.weights({'r1': 'management', 'r2': 'stack', 'r3': 'stack'})
        swapped = self.weights({'r1': 'stack', 'r2': 'management', 'r3': 'stack'})
        self.assertEqual(first, swapped)


if __name__ == '__main__':
    unittest.main()
