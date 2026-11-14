"""Make reference replay reports for testing the evaluator itself."""

import argparse
import asyncio
import json
from pathlib import Path

from prototype.analysis_contracts import ResumeAnalysis, VacancyAnalysis
from prototype.candidate_profile import CandidateProfile, ClaimSource, ConditionComparison, Conditions
from prototype.contracts import Fact, Requirement, Requirements, Row
from prototype.demo import SyntheticPrivacy
from prototype.errors import ModelOutputError
from prototype.pipeline import run_pipeline

from .saved_reports import DEFAULT_EXPECTATIONS, load_expectations


def mandatory_excerpt(text, quote):
    start = text.rfind('Обязательно:', 0, text.index(quote))
    if start < 0:
        raise ValueError('example_missing_mandatory_heading')
    return text[start:text.index(quote) + len(quote)]


def responses_for(case, wrong_evidence_key):
    texts = {job['job_id']: job['text'] for job in case['vacancies']}
    facts = {}
    responses = {}

    def fact_for(quote):
        if quote not in facts:
            facts[quote] = Fact(id=f'f{len(facts)+1}', text=quote, quote=quote)
        return facts[quote]

    for jid, text in texts.items():
        if jid in case['unprocessed_job_ids']:
            continue
        requirements, rows = [], []
        for ref in case['requirements']:
            if ref['job_id'] != jid:
                continue
            rid, quote = ref['key'], ref['quote']
            marker = mandatory_excerpt(text, quote) if ref['mandatory'] else None
            requirements.append(Requirement(id=rid, text=quote, quote=quote, mandatory_quote=marker))
            status = ref['allowed_status'][0]
            fact_ids = []
            if status != 'unknown':
                selected = ref['cv_quotes'][0]
                if rid == wrong_evidence_key:
                    selected = next(line for line in case['cv_text'].splitlines()
                                    if not any(quote in line or line in quote for quote in ref['cv_quotes']))
                fact_ids = [fact_for(selected).id]
            rows.append(Row(requirement_id=rid, status=status, fact_ids=fact_ids,
                            comment='Вымышленный ответ для проверки раннера.',
                            question=None if status == 'full' else 'Уточните сведения по требованию.'))
        conditions = []
        for ref in case['conditions']:
            if ref['job_id'] != jid:
                continue
            if ref['kind'] != 'work_mode':
                raise ValueError('unexpected_reference_condition')
            allowed = ref['allowed_states']
            state = 'unknown' if 'unknown' in allowed else allowed[0]
            vacancy_quote = next(line for line in text.splitlines() if line.startswith('Формат работы:'))
            cv = None
            if state != 'unknown':
                quote = 'Рассматриваю только удалённую работу.'
                if quote not in case['cv_text']:
                    raise ValueError('example_missing_work_mode')
                cv = ClaimSource(fact_id=fact_for(quote).id, quote=quote)
            conditions.append(ConditionComparison(kind='work_mode', state=state, cv=cv,
                                                  vacancy_quote=vacancy_quote, note=ref['rationale']))
        responses[text] = (Requirements(items=requirements),
                           VacancyAnalysis(rows=rows, conditions=Conditions(items=conditions)))
    profile = CandidateProfile(summary=[], stack=[], last_position=None, achievements=[],
                               missing=['summary', 'stack', 'last_position', 'achievements'])
    return ResumeAnalysis(items=list(facts.values()), profile=profile), responses


class ReferenceReplay:
    def __init__(self, facts, responses):
        self.facts = facts
        self.responses = responses
        self.evaluation = None

    async def ask(self, schema, task, payload):
        if task == 'facts':
            return self.facts
        if task == 'requirements':
            if payload['text'] not in self.responses:
                raise ModelOutputError('synthetic_expected_failure')
            requirements, self.evaluation = self.responses[payload['text']]
            return requirements
        if task == 'evaluation':
            return self.evaluation
        raise ValueError('unexpected_replay_task')


def example_report(case, *, wrong_evidence_key=None):
    replay = ReferenceReplay(*responses_for(case, wrong_evidence_key))
    jobs = [(job['job_id'], job['text']) for job in case['vacancies']]
    report = asyncio.run(run_pipeline(case['cv_text'], jobs, replay, SyntheticPrivacy()))
    report.update(mode='synthetic_replay_NOT_model_output', model=None)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expectations', type=Path, default=DEFAULT_EXPECTATIONS)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--wrong-evidence', action='store_true', help='Give E6-FE-01 an unrelated, literal résumé quote.')
    args = parser.parse_args(argv)
    cases = load_expectations(args.expectations)
    args.out.mkdir(parents=True, exist_ok=True)
    for case in cases:
        key = 'fe-react' if args.wrong_evidence and case['case_id'] == 'E6-FE-01' else None
        report = example_report(case, wrong_evidence_key=key)
        path = args.out / (case['case_id'] + '.json')
        with path.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    print(f'Синтетических отчётов: {len(cases)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
