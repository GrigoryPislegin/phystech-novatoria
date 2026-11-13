"""Fictional skill-only documents. Replay values are handwritten, NOT model output."""
from .contracts import Facts, Fact, Requirements, Requirement, Evaluation, Row


def demo_inputs(scenario='success'):
    if scenario not in {'success', 'disputed'}:
        raise ValueError('unknown_demo_scenario')
    return ('Разрабатывал на Python 3 года. Использовал SQL 1 год.', [
        ('job-001', 'Python обязателен. SQL желателен.' if scenario == 'success'
         else 'Обязателен опыт Python и Go.'),
        ('job-002', 'Java обязателен.'),
        ('job-003', 'SQL: обязательно не менее 3 лет опыта.'),
    ])


class SyntheticPrivacy:
    """Only used by CLI for the fixed documents above; never offered for user files."""
    async def redact(self, text): return text
    async def check(self, text): pass


class ReplayModel:
    def __init__(self): self.calls = 0

    async def ask(self, schema, task, payload):
        self.calls += 1
        result = (await self._answer(task, payload)).model_dump()
        if task == 'facts' and 'profile' in schema.model_fields:
            def claim(text, fact_id, quote):
                return {'text':text, 'sources':[{'fact_id':fact_id, 'quote':quote}]}
            result['profile'] = {
                'summary':[claim('Разрабатывал на Python 3 года.', 'f1', 'Разрабатывал на Python 3 года.')],
                'stack':[claim('Python', 'f1', 'Python'), claim('SQL', 'f2', 'SQL')],
                'last_position':None, 'achievements':[], 'missing':['last_position','achievements']}
        if task == 'evaluation' and 'conditions' in schema.model_fields:
            result['conditions'] = {'items':[]}
        return schema.model_validate(result)

    async def _answer(self, task, payload):
        if task == 'facts':
            return Facts(items=[Fact(id='f1', text='Python 3 года', quote='Разрабатывал на Python 3 года.'),
                                Fact(id='f2', text='SQL 1 год', quote='Использовал SQL 1 год.')])
        if task == 'requirements':
            text = payload['text']
            if 'Python и Go' in text:
                return Requirements(items=[Requirement(id='r1', text='Опыт Python и Go',
                    quote=text, mandatory_quote=text)])
            if 'Python' in text:
                return Requirements(items=[Requirement(id='r1',text='Python',quote='Python обязателен.',mandatory_quote='Python обязателен.'),
                                           Requirement(id='r2',text='SQL',quote='SQL желателен.',mandatory_quote=None)])
            return Requirements(items=[Requirement(id='r1',text=text,quote=text,mandatory_quote=text)])
        items = payload['requirements']['items']
        if len(items) == 2:
            return Evaluation(rows=[Row(requirement_id='r1',status='full',fact_ids=['f1'],comment='Опыт Python указан.',question=None),
                                    Row(requirement_id='r2',status='full',fact_ids=['f2'],comment='Опыт SQL указан.',question=None)])
        if 'Python и Go' in items[0]['text']:
            return Evaluation(rows=[Row(requirement_id='r1', status='partial', fact_ids=['f1'],
                comment='Python подтверждён; опыт Go не указан, составное требование подтверждено частично.',
                question='Есть ли опыт Go? Уточните проекты и продолжительность.')])
        java = 'Java' in items[0]['text']
        return Evaluation(rows=[Row(requirement_id='r1',status='unknown' if java else 'fail',fact_ids=[] if java else ['f2'],
                                    comment='Java не указан.' if java else 'Указан 1 год SQL, требуется не менее 3.',
                                    question='Есть опыт Java?' if java else 'Есть дополнительный опыт SQL, не включённый в резюме?')])
