"""E5: candidate profile, CV↔vacancy conditions and requirement factors. Synthetic data only."""
import json
import unittest
from pathlib import Path

from prototype.candidate_profile import (INTEGRATED, CandidateProfile, Conditions, check_conditions,
                                         check_profile)
from prototype.contracts import Fact, Facts, RequirementFactors, Requirements
from prototype.evidence import Source

FIXTURES = Path(__file__).resolve().parents[2] / 'docs' / 'reviews' / 'egor-e5-fixtures.json'


def load():
    return {f['fixture_id']: f for f in json.loads(FIXTURES.read_text(encoding='utf-8'))['fixtures']}


def parts(fixture, **profile_update):
    facts = Facts.model_validate(fixture['facts'])
    profile = CandidateProfile.model_validate({**fixture['profile'], **profile_update})
    return profile, facts, Source.of('cv', fixture['cv_text'])


def codes(findings):
    return {f.code for f in findings}


def claim(fact_id, quote, text=None):
    return {'text': text or quote, 'sources': [{'fact_id': fact_id, 'quote': quote}]}


class FixtureTests(unittest.TestCase):
    def test_fixtures_are_valid_against_their_texts(self):
        for fid, f in load().items():
            with self.subTest(fid):
                facts = Facts.model_validate(f['facts'])
                facts.validate_source(f['cv_text'])
                requirements = Requirements.model_validate(f['requirements'])
                requirements.validate_source(f['vacancy_text'])
                RequirementFactors.model_validate(f['factors']).validate_requirements(requirements)
                self.assertEqual(f['decision_status'], 'draft')

    def test_profile_and_conditions_match_expectations(self):
        for fid, f in load().items():
            with self.subTest(fid):
                profile, facts, cv = parts(f)
                self.assertEqual(check_profile(profile, facts, cv).state, f['expected']['profile_state'])
                result = check_conditions(Conditions.model_validate(f['conditions']), facts, cv,
                                          Source.of(f['vacancy_id'], f['vacancy_text']))
                self.assertEqual({c.kind: c.check for c in result.items}, f['expected']['conditions'])
                self.assertEqual(result.conflicts, f['expected']['conflicts'])
                self.assertFalse(result.has_invalid)

    def test_every_claim_is_located_in_the_cv(self):
        profile, facts, cv = parts(load()['P1'])
        spans = check_profile(profile, facts, cv).spans
        self.assertEqual(len(spans), 9)
        for where, located in spans.items():
            with self.subTest(where):
                self.assertTrue(located)
                for span in located:
                    self.assertEqual(cv.text[span.start:span.end], span.quote)

    def test_negated_skill_is_absent_from_expected_stack(self):
        p2 = load()['P2']
        self.assertNotIn('Python', [c['text'] for c in p2['profile']['stack']])
        self.assertEqual(p2['expected']['evaluation']['r1']['allowed'], ['fail'])


class ProfileCheckTests(unittest.TestCase):
    def test_invented_metric_is_invalid(self):
        p1 = load()['P1']
        result_claim = claim('f5', 'с 800 до 200 мс', 'ускорил на 75%')
        achievements = [{'action': claim('f5', 'Сократил время ответа API'), 'result': result_claim}]
        profile, facts, cv = parts(p1, achievements=achievements)
        check = check_profile(profile, facts, cv)
        self.assertEqual(check.state, 'invalid')
        self.assertIn('number_not_in_source', codes(check.findings))

    def test_reformatted_number_is_accepted(self):
        p1 = load()['P1']
        profile, facts, cv = parts(p1, summary=[claim('f7', 'от 250 000 рублей в месяц', 'от 250000 рублей')])
        self.assertEqual(check_profile(profile, facts, cv).state, 'structure_ok')

    def test_last_position_needs_dates(self):
        p2 = load()['P2']
        guessed = {'role': claim('f4', 'аналитиком'), 'domain': claim('f4', 'в банке'),
                   'period': claim('f4', 'Работал аналитиком в банке')}
        profile, facts, cv = parts(p2, last_position=guessed, missing=[])
        check = check_profile(profile, facts, cv)
        self.assertEqual(check.state, 'invalid')
        self.assertIn('undated_last_position', codes(check.findings))

    def test_later_year_in_cv_sends_last_position_to_review(self):
        p1 = load()['P1']
        older = {'role': claim('f3', 'разработчик'), 'domain': claim('f3', 'интернет-магазин'),
                 'period': claim('f3', '2019–2021', '2019–2021')}
        profile, facts, cv = parts(p1, last_position=older)
        self.assertEqual(check_profile(profile, facts, cv).state, 'structure_ok')  # 2021 is the latest year
        later = Facts(items=facts.items + [Fact(id='f9', text='Курс Kafka', quote='Курс по Kafka, 2024.')])
        check = check_profile(profile, later, Source.of('cv', cv.text + '\nКурс по Kafka, 2024.'))
        self.assertEqual(check.state, 'needs_review')
        self.assertIn('later_period_in_cv', codes(check.findings))

    def test_period_cannot_be_borrowed_from_another_fact(self):
        p2 = load()['P2']
        facts = Facts.model_validate(p2['facts'])
        facts = Facts(items=facts.items + [Fact(id='f7', text='Вуз', quote='Окончил вуз в 2015.')])
        cv = Source.of('cv', p2['cv_text'] + '\nОкончил вуз в 2015.')
        borrowed = {'role': claim('f4', 'аналитиком'), 'domain': None, 'period': claim('f7', '2015')}
        profile = CandidateProfile.model_validate({**p2['profile'], 'last_position': borrowed, 'missing': []})
        check = check_profile(profile, facts, cv)
        self.assertEqual(check.state, 'invalid')
        self.assertIn('period_not_bound_to_role', codes(check.findings))

    def test_count_is_not_a_year(self):
        p1 = load()['P1']
        facts = Facts(items=Facts.model_validate(p1['facts']).items
                      + [Fact(id='f8', text='Нагрузка', quote='2000 запросов в секунду, тимлид.')])
        cv = Source.of('cv', p1['cv_text'] + '\n2000 запросов в секунду, тимлид.')
        counted = {'role': claim('f8', 'тимлид'), 'domain': None, 'period': claim('f8', '2000 запросов')}
        profile = CandidateProfile.model_validate({**p1['profile'], 'last_position': counted})
        self.assertIn('undated_last_position', codes(check_profile(profile, facts, cv).findings))

    def test_later_year_missing_from_facts_still_counts(self):
        profile, facts, cv = parts(load()['P1'])
        check = check_profile(profile, facts, Source.of('cv', cv.text + '\n2024 — тимлид, финтех.'))
        self.assertIn('later_period_in_cv', codes(check.findings))

    def test_report_shows_quote_when_text_is_paraphrase(self):
        p1 = load()['P1']
        role = claim('f4', 'ведущий разработчик', 'ведущий разработчик в крупном банке')
        position = {**p1['profile']['last_position'], 'role': role}
        profile, facts, cv = parts(p1, last_position=position)
        check = check_profile(profile, facts, cv)
        self.assertEqual(check.state, 'structure_ok')  # paraphrase without digits is not caught here
        self.assertEqual(check.display['last_position.role'], 'ведущий разработчик')
        self.assertEqual(check.display['stack[0]'], 'Python')

    def test_numbers_split_across_sources(self):
        p1 = load()['P1']
        result = {'text': 'с 800 до 200 мс', 'sources': [{'fact_id': 'f5', 'quote': 'с 800'},
                                                         {'fact_id': 'f5', 'quote': '200 мс'}]}
        achievements = [{'action': claim('f5', 'Сократил время ответа API'), 'result': result}]
        profile, facts, cv = parts(p1, achievements=achievements)
        self.assertEqual(check_profile(profile, facts, cv).state, 'structure_ok')

    def test_missing_must_match_filled_sections(self):
        p2 = load()['P2']
        profile, facts, cv = parts(p2, missing=[])
        self.assertIn('missing_mismatch', codes(check_profile(profile, facts, cv).findings))
        profile, facts, cv = parts(p2, missing=['last_position', 'stack'])
        self.assertIn('missing_mismatch', codes(check_profile(profile, facts, cv).findings))
        profile, facts, cv = parts(p2, missing=['last_position', 'last_position'])
        self.assertIn('duplicate_section', codes(check_profile(profile, facts, cv).findings))

    def test_claim_sources_must_exist(self):
        p1 = load()['P1']
        profile, facts, cv = parts(p1, stack=[claim('f99', 'Python')])
        self.assertIn('unknown_fact_id', codes(check_profile(profile, facts, cv).findings))
        profile, facts, cv = parts(p1, stack=[claim('f2', 'Kotlin')])
        self.assertIn('quote_not_in_fact', codes(check_profile(profile, facts, cv).findings))

    def test_repeated_fact_in_different_places_is_not_resolved_silently(self):
        p1 = load()['P1']
        profile, facts, _ = parts(p1)
        cv = Source.of('cv', p1['cv_text'] + '\nНе использую:\n- Навыки: Python, Django, PostgreSQL.')
        check = check_profile(profile, facts, cv)
        self.assertEqual(check.state, 'needs_review')
        self.assertIn('ambiguous_location', codes(check.findings))

    def test_profile_schema_has_no_personal_fields_and_is_strict(self):
        fields = set(CandidateProfile.model_fields)
        self.assertEqual(fields, {'summary', 'stack', 'last_position', 'achievements', 'missing'})
        for model in (CandidateProfile, Conditions, RequirementFactors):
            schema = model.model_json_schema()
            for name, node in [('root', schema), *schema.get('$defs', {}).items()]:
                with self.subTest(model=model.__name__, node=name):
                    self.assertFalse(node.get('additionalProperties', False))
                    self.assertEqual(set(node.get('required', [])), set(node.get('properties', {})))


class ConditionsCheckTests(unittest.TestCase):
    def setUp(self):
        p2 = load()['P2']
        self.facts = Facts.model_validate(p2['facts'])
        self.cv = Source.of('cv', p2['cv_text'])
        self.vacancy = Source.of('job-p2', p2['vacancy_text'])

    def run_check(self, *items):
        return check_conditions(Conditions(items=list(items)), self.facts, self.cv, self.vacancy)

    def item(self, kind, state, cv=None, vacancy_quote=None):
        return {'kind': kind, 'state': state, 'cv': cv, 'vacancy_quote': vacancy_quote, 'note': 'синтетика'}

    def test_compatible_or_conflict_needs_both_quotes(self):
        result = self.run_check(self.item('location', 'conflict', cv={'fact_id': 'f6', 'quote': 'в Казани'}))
        self.assertIn('one_sided_comparison', codes(result.items[0].findings))
        self.assertTrue(result.has_invalid)

    def test_unknown_may_have_one_side(self):
        result = self.run_check(self.item('location', 'unknown', cv={'fact_id': 'f6', 'quote': 'в Казани'}))
        self.assertEqual(result.items[0].check, 'structure_ok')

    def test_unknown_with_both_sides_goes_to_review(self):
        result = self.run_check(self.item('location', 'unknown', cv={'fact_id': 'f6', 'quote': 'в Казани'},
                                          vacancy_quote='офис в Москве'))
        self.assertEqual(result.items[0].check, 'needs_review')
        self.assertIn('unknown_with_both_sides', codes(result.items[0].findings))

    def test_conflict_is_highlighted_not_rejected(self):
        result = self.run_check(self.item('location', 'conflict', cv={'fact_id': 'f6', 'quote': 'в Казани'},
                                          vacancy_quote='офис в Москве'))
        self.assertEqual(result.conflicts, ['location'])
        self.assertEqual(result.items[0].check, 'needs_review')
        self.assertFalse(result.has_invalid)

    def test_vacancy_quote_must_exist(self):
        result = self.run_check(self.item('location', 'unknown', vacancy_quote='Санкт-Петербург'))
        self.assertIn('quote_not_found', codes(result.items[0].findings))

    def test_duplicate_kind_is_invalid(self):
        result = self.run_check(self.item('relocation', 'unknown'), self.item('relocation', 'unknown'))
        self.assertIn('duplicate_kind', codes(result.findings))
        self.assertTrue(result.has_invalid)


class FactorTests(unittest.TestCase):
    def setUp(self):
        self.requirements = Requirements.model_validate(load()['P1']['requirements'])

    def test_missing_entry_is_other(self):
        factors = RequirementFactors.model_validate({'items': [{'requirement_id': 'r3', 'factor': 'domain'}]})
        factors.validate_requirements(self.requirements)
        self.assertEqual([factors.factor_of(r.id) for r in self.requirements.items], ['other', 'other', 'domain'])

    def test_unknown_or_duplicate_ids_are_rejected(self):
        for items, code in [([{'requirement_id': 'r9', 'factor': 'stack'}], 'unknown_requirement_id'),
                            ([{'requirement_id': 'r1', 'factor': 'stack'}] * 2, 'duplicate_ids')]:
            with self.subTest(code), self.assertRaisesRegex(ValueError, code):
                RequirementFactors.model_validate({'items': items}).validate_requirements(self.requirements)


class FlagTests(unittest.TestCase):
    def test_integrated(self):
        self.assertTrue(INTEGRATED)


if __name__ == '__main__':
    unittest.main()
