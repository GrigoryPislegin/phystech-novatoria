"""Conservative display projections from structurally validated pipeline results.

Free model prose remains in evaluation for audit, never as verified brief text.
This projection does not establish entailment or completeness of extraction.
"""

EXPLANATIONS = {
    'full':'Модель предложила полное соответствие; проверьте смысл приведённых цитат.',
    'partial':'Модель предложила частичное соответствие; уточните непокрытые части требования.',
    'fail':'Модель предложила несоответствие; проверьте противоречие до решения о кандидате.',
    'unknown':'Подтверждающие сведения не указаны в извлечённых фактах; это не доказательство отсутствия опыта.',
}


def gap_question(status, requirement_quote):
    if status == 'full':
        return None
    return f'Уточните опыт по требованию «{requirement_quote}»: какие задачи выполняли, когда и с каким результатом?'


def display_label(requirement):
    # A paraphrase can contain invented qualifications even if its quote is real.
    label = requirement['text']
    return label if label in requirement['quote'] else requirement['quote']


def build_presentation(report):
    facts = {f['id']:f for f in report['facts']['items']}
    jobs = []
    for job in report['ranking']['jobs']:
        requirements = {r['id']:r for r in job['requirements']['items']}
        evidence = {r['requirement_id']:r for r in job.get('evidence_check', {}).get('rows', [])}
        mandatory_checks = {r['requirement_id']:r for r in job.get('evidence_check', {}).get('mandatory', [])}
        excluded = job.get('score_review', {}).get('excluded_mandatory_ids', [])
        rows = []
        for row in job['evaluation']['rows']:
            req = requirements[row['requirement_id']]
            rows.append({'requirement_id':req['id'], 'label':display_label(req),
                         'requirement_quote':req['quote'], 'mandatory_quote':req['mandatory_quote'],
                         'mandatory_verification':'not_reviewed',
                         'mandatory_check':mandatory_checks.get(req['id']),
                         'mandatory_applied_to_score':bool(req['mandatory_quote']) and req['id'] not in excluded, 'status':row['status'],
                         'status_verification':'model_proposed',
                         'evidence_check':evidence.get(req['id']),
                         'resume_quotes':[facts[f]['quote'] for f in row['fact_ids']],
                         'explanation':EXPLANATIONS[row['status']],
                         'question':gap_question(row['status'], req['quote'])})
        jobs.append({'job_id':job['job_id'], 'rank':job['rank'], 'score':job['score'], 'rows':rows,
                     'score_review':job.get('score_review'),
                     'requirements_draft':job.get('requirements_draft'),
                     'requirements_review':job.get('requirements_review'),
                     'manager_brief':{'state':'draft_requires_review', 'final_allowed':False,
                         'processing_complete':report['ranking']['complete'],
                         'grounds':[r for r in rows if r['status']=='full'][:3],
                         'risks':[r for r in rows if r['status']!='full'],
                         'questions':[r['question'] for r in sorted(rows, key=lambda r: not bool(r['mandatory_quote'])) if r['question']][:5]}})
    return {'version':'0.1', 'jobs':jobs, 'final_allowed':False}
