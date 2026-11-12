"""Fictional skill-only documents. Replay values are handwritten, NOT model output."""
from .contracts import Facts, Fact, Requirements, Requirement, Evaluation, Row


def demo_inputs():
    return ('Разрабатывал на Python 3 года. Использовал SQL 1 год.', [
        ('job-001', 'Python обязателен. SQL желателен.'),
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
        if task == 'facts':
            return Facts(items=[Fact(id='f1', text='Python 3 года', quote='Разрабатывал на Python 3 года.'),
                                Fact(id='f2', text='SQL 1 год', quote='Использовал SQL 1 год.')])
        if task == 'requirements':
            text = payload['text']
            if 'Python' in text:
                return Requirements(items=[Requirement(id='r1',text='Python',quote='Python обязателен.',mandatory_quote='Python обязателен.'),
                                           Requirement(id='r2',text='SQL',quote='SQL желателен.',mandatory_quote=None)])
            return Requirements(items=[Requirement(id='r1',text=text,quote=text,mandatory_quote=text)])
        items = payload['requirements']['items']
        if len(items) == 2:
            return Evaluation(rows=[Row(requirement_id='r1',status='full',fact_ids=['f1'],comment='Опыт Python указан.',question=None),
                                    Row(requirement_id='r2',status='full',fact_ids=['f2'],comment='Опыт SQL указан.',question=None)])
        java = 'Java' in items[0]['text']
        return Evaluation(rows=[Row(requirement_id='r1',status='unknown' if java else 'fail',fact_ids=[] if java else ['f2'],
                                    comment='Java не указан.' if java else 'Указан 1 год SQL, требуется не менее 3.',
                                    question='Есть опыт Java?' if java else 'Есть дополнительный опыт SQL, не включённый в резюме?')])
