"""E15 urgent check: short counterexamples for the evidence check (rules evidence-0.4).

A structural check cannot judge meaning; it can refuse to count a `full` claim whose quotes do not
even contain what the requirement names. Synthetic texts; nothing here measures a model.
"""
import unittest

from prototype.contracts import Evaluation, Fact, Facts, Requirement, Requirements, Row
from prototype.evidence import Source, check_pair
from prototype.scoring import score


def run(requirement, cv, quote, status, *, mandatory=True):
    vacancy = requirement
    reqs = Requirements(items=[Requirement(id='r1', text=requirement, quote=requirement,
                                           mandatory_quote=requirement if mandatory else None)])
    facts = Facts(items=[Fact(id='f1', text='факт', quote=quote)])
    evaluation = Evaluation(rows=[Row(requirement_id='r1', status=status, fact_ids=['f1'], comment='c',
                                      question=None if status == 'full' else 'q')])
    evidence = check_pair(reqs, facts, evaluation, Source.of('cv', cv), Source.of('job', vacancy))
    return score(reqs, evaluation, evidence), evidence.rows[0]


def codes(check):
    return {r.code for r in check.reasons}


class NamedTermTests(unittest.TestCase):
    def refused(self, requirement, cv, code='requirement_part_not_cited'):
        s, check = run(requirement, cv, cv, 'full')
        self.assertEqual(check.state, 'needs_review', (requirement, cv))
        self.assertIn(code, codes(check))
        self.assertEqual((s['lower'], s['mandatory']), (0, 'clarify'))  # to the recruiter, never a fail
        return check

    def counted(self, requirement, cv, status='full'):
        s, check = run(requirement, cv, cv, status)
        self.assertEqual((check.state, codes(check)), ('structure_ok', set()), (requirement, cv))
        return s

    def test_1_vue_and_nuxt_do_not_show_commercial_react(self):
        cv = 'Разрабатывал интерфейсы на Vue и Nuxt 3 года.'
        self.refused('Коммерческий опыт React.', cv, 'evidence_not_linked')
        check = self.refused('Опыт разработки интерфейсов на React.', cv)  # a shared ordinary word is not enough
        self.assertIn('React', check.reasons[0].message)
        self.counted('Опыт разработки интерфейсов на React.', 'Разрабатывал интерфейсы на React 3 года.')

    def test_2_seven_years_of_frontend_do_not_show_managing_eighty_people(self):
        self.refused('Управление командой от 80 сотрудников.', 'Frontend-разработчик, 7 лет.', 'evidence_not_linked')

    def test_3_a_compound_requirement_is_full_only_when_every_part_is_cited(self):
        self.refused('Опыт Python и Go.', 'Писал на Python 4 года.')
        self.refused('Опыт с Docker, Kubernetes и Kafka.', 'Разворачивал сервисы в Docker и Kafka.')
        self.counted('Опыт Python и Go.', 'Писал на Python и Go 4 года.')
        s = self.counted('Опыт Python и Go.', 'Писал на Python 4 года.', status='partial')  # that is what partial is
        self.assertEqual(s['lower'], 50)
        self.counted('Опыт Django или FastAPI.', 'Писал сервисы на FastAPI.')  # a choice needs one of them
        self.counted('Опыт Vue.js.', 'Писал на Vue.js 2 года.')

    def test_4_b1_is_a_stated_gap_for_a_mandatory_b2_and_silence_is_unknown(self):
        self.refused('Английский язык не ниже B2.', 'Английский язык — B1.')  # B1 offered as full
        s, check = run('Английский язык не ниже B2.', 'Английский язык — B1.', 'Английский язык — B1.', 'fail')
        self.assertEqual((check.state, s['mandatory'], s['breakdown']['stop_factors']), ('structure_ok', 'violated', ['r1']))
        self.counted('Английский язык не ниже B1.', 'Английский язык — B2.')  # a higher level covers a lower one
        self.counted('Английский язык не ниже B2.', 'Английский язык — C1.')
        # No language in the resume: the model must answer unknown, and unknown never violates.
        reqs = Requirements(items=[Requirement(id='r1', text='Английский B2', quote='Английский язык не ниже B2.',
                                               mandatory_quote='Английский язык не ниже B2.')])
        evaluation = Evaluation(rows=[Row(requirement_id='r1', status='unknown', fact_ids=[], comment='c', question='q')])
        evidence = check_pair(reqs, Facts(items=[]), evaluation, Source.of('cv', 'Писал на Python.'),
                              Source.of('job', 'Английский язык не ниже B2.'))
        s = score(reqs, evaluation, evidence)
        self.assertEqual((s['mandatory'], s['lower'], s['upper'], s['breakdown']['stop_factors']), ('clarify', 0, 100, []))

    def test_5_a_bank_client_does_not_show_soc_analytics(self):
        cv = 'Заказчик — банк, внедрял CRM.'
        self.refused('Опыт SOC-аналитики.', cv, 'evidence_not_linked')
        self.refused('Опыт аналитики SOC в банке.', cv, 'evidence_not_linked')
        self.refused('Опыт SOC и CRM.', cv)  # «CRM» is cited, «SOC» is not

    def test_6_a_junior_vacancy_is_scored_by_its_requirements_only(self):
        # A senior resume against junior requirements: no hidden penalty for being overqualified.
        s = self.counted('Знание Python.', 'Ведущий разработчик, 8 лет писал на Python.')
        self.assertEqual((s['lower'], s['upper'], s['mandatory']), (100, 100, 'confirmed'))


if __name__ == '__main__':
    unittest.main()
