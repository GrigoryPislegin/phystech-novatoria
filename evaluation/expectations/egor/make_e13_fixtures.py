"""Generate the E13 integration fixtures and expectations. Fully fictional documents.

python evaluation/expectations/egor/make_e13_fixtures.py

Writes evaluation/fixtures/integration/egor-e13-<name>.json (documents and handwritten "model
answers" in the wire DTOs) and evaluation/expectations/egor/e13-cases.json (the team's draft
expectations). Every quote is checked to be an exact fragment of its document, every DTO is
validated by the real contracts, and every reference must resolve, so a typo fails here and not
in a test. The answers are written by hand: they are not model output and measure no model.

A requirement line is `(text, quote, mandatory, status, fact_ids, comment)`; mandatory is False,
True (the line states it itself, so the marker is the line) or a longer marker quote.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from prototype.analysis_contracts import ResumeAnalysis, VacancyAnalysis  # noqa: E402
from prototype.contracts import Facts, Requirements, validate_pair  # noqa: E402

OUT = ROOT / 'evaluation' / 'fixtures' / 'integration'
EXPECT = Path(__file__).parent / 'e13-cases.json'


def claim(text, fact_id, quote):
    return {'text': text, 'sources': [{'fact_id': fact_id, 'quote': quote}]}


def vacancy(job_id, title, text, lines, conditions=()):
    requirements, rows = [], []
    for i, (name, quote, mandatory, status, fact_ids, comment) in enumerate(lines, 1):
        assert quote in text, (job_id, quote)
        marker = quote if mandatory is True else mandatory or None
        assert marker is None or (marker in text and quote in marker and len(marker) >= 8), (job_id, marker)
        requirements.append({'id': f'r{i}', 'text': name, 'quote': quote, 'mandatory_quote': marker})
        rows.append({'requirement_id': f'r{i}', 'status': status, 'fact_ids': list(fact_ids), 'comment': comment,
                     'question': None if status == 'full' else f'Уточните опыт по требованию «{name}».'})
    for item in conditions:
        assert item['vacancy_quote'] is None or item['vacancy_quote'] in text, (job_id, item['vacancy_quote'])
    return {'job_id': job_id, 'title': title, 'text': text, 'requirements': {'items': requirements},
            'evaluation': {'rows': rows, 'conditions': {'items': list(conditions)}}}


def build(name, domain, cv_text, facts, profile, vacancies):
    for fact in facts:
        assert fact['quote'] in cv_text, (name, fact['id'], fact['quote'])
    by_id = {f['id']: f['quote'] for f in facts}

    def sources(node):
        if isinstance(node, dict):
            if set(node) == {'fact_id', 'quote'}:
                assert node['quote'] in by_id[node['fact_id']], (name, node)
            for child in node.values():
                sources(child)
        elif isinstance(node, list):
            for child in node:
                sources(child)

    sources(profile)
    analysis = ResumeAnalysis.model_validate({'items': facts, 'profile': profile})
    Facts(items=analysis.items).validate_source(cv_text)
    for v in vacancies:
        requirements = Requirements.model_validate(v['requirements'])
        requirements.validate_source(v['text'])
        assessed = VacancyAnalysis.model_validate(v['evaluation'])
        validate_pair(requirements, Facts(items=analysis.items), assessed)
        sources(v['evaluation']['conditions'])
    fixture = {
        'schema_version': 'egor-e13-fixture-0.1', 'case_id': f'E13-{name}', 'domain': domain, 'synthetic': True,
        'note': 'Полностью вымышленные документы и рукописные ответы в wire-DTO. Не вывод модели; '
                'качество LLM этим не измеряется. Цитаты заданы по исходному тексту, харнесс переносит их '
                'на текст после защиты данных.',
        'cv_text': cv_text,
        'vacancies': [{'job_id': v['job_id'], 'title': v['title'], 'text': v['text']} for v in vacancies],
        'model': {'facts': {'items': facts, 'profile': profile},
                  'requirements': {v['job_id']: v['requirements'] for v in vacancies},
                  'evaluation': {v['job_id']: v['evaluation'] for v in vacancies}}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f'egor-e13-{name}.json').write_text(json.dumps(fixture, ensure_ascii=False, indent=1) + '\n',
                                               encoding='utf-8')
    stats = (len(facts), [len(v['requirements']['items']) for v in vacancies])
    print(f'egor-e13-{name}.json facts={stats[0]} requirements={stats[1]}')
    return fixture


# ---------- minimal: the first reproducible fixture ------------------------------------------------

MIN_CV = """Орлова Ксения Павловна
Телефон: +7 (900) 000-00-01, email: ksenia.synthetic@example.com
Аналитик данных, 4 года опыта.
2021–2023 — младший аналитик, ООО «Северный Вектор». Писала запросы на SQL к PostgreSQL, готовила отчёты в Excel.
2023 — по настоящее время — аналитик данных, АО «Балтийские Линии». Построила дашборд продаж в Power BI, сократила подготовку еженедельного отчёта с 6 до 2 часов.
С Python не работала, прохожу курс.
Рассматриваю только удалённую работу."""

MIN_FACTS = [
    {'id': 'f1', 'text': 'Аналитик данных, 4 года опыта', 'quote': 'Аналитик данных, 4 года опыта.'},
    {'id': 'f2', 'text': 'Запросы на SQL, отчёты в таблицах',
     'quote': 'Писала запросы на SQL к PostgreSQL, готовила отчёты в Excel.'},
    {'id': 'f3', 'text': 'Аналитик данных с 2023 года',
     'quote': '2023 — по настоящее время — аналитик данных, АО «Балтийские Линии».'},
    {'id': 'f4', 'text': 'Дашборд продаж, отчёт быстрее',
     'quote': 'Построила дашборд продаж в Power BI, сократила подготовку еженедельного отчёта с 6 до 2 часов.'},
    {'id': 'f5', 'text': 'С языком программирования не работала, проходит курс',
     'quote': 'С Python не работала, прохожу курс.'},
    {'id': 'f6', 'text': 'Только удалённая работа', 'quote': 'Рассматриваю только удалённую работу.'},
]

MIN_PROFILE = {
    'summary': [claim('Аналитик данных, 4 года опыта', 'f1', 'Аналитик данных, 4 года опыта')],
    'stack': [claim('SQL', 'f2', 'SQL')],
    'last_position': {'role': claim('аналитик данных', 'f3', 'аналитик данных'), 'domain': None,
                      'period': claim('2023 — по настоящее время', 'f3', '2023 — по настоящее время')},
    'achievements': [{'action': claim('Построила дашборд продаж', 'f4', 'Построила дашборд продаж'),
                      'result': claim('с 6 до 2 часов', 'f4', 'с 6 до 2 часов')}],
    'missing': [],
}

MIN_JOB_A = """Аналитик данных
Обязателен опыт написания запросов на SQL от 2 лет.
Обязательно умение строить дашборды.
Желателен опыт работы с Python.
Формат работы: удалённо."""

MIN_JOB_B = """Разработчик отчётности
Обязателен коммерческий опыт разработки на Python от 1 года.
Желательно знание Airflow.
Работа в офисе."""


def minimal():
    return build('minimal', 'analytics', MIN_CV, MIN_FACTS, MIN_PROFILE, [
        vacancy('job-a', 'Аналитик данных', MIN_JOB_A, [
            ('Запросы на SQL от 2 лет', 'Обязателен опыт написания запросов на SQL от 2 лет.', True, 'full',
             ['f1', 'f2'], 'Запросы на SQL указаны, общий стаж аналитика 4 года.'),
            ('Дашборды', 'Обязательно умение строить дашборды.', True, 'full', ['f4'],
             'Построен дашборд продаж.'),
            ('Опыт с языком программирования', 'Желателен опыт работы с Python.', False, 'fail', ['f5'],
             'В резюме прямо сказано, что опыта нет.'),
        ], conditions=[{'kind': 'work_mode', 'state': 'compatible',
                        'cv': {'fact_id': 'f6', 'quote': 'только удалённую работу'},
                        'vacancy_quote': 'Формат работы: удалённо.', 'note': 'Обе стороны называют удалённый формат.'}]),
        vacancy('job-b', 'Разработчик отчётности', MIN_JOB_B, [
            ('Коммерческая разработка от 1 года', 'Обязателен коммерческий опыт разработки на Python от 1 года.',
             True, 'fail', ['f5'], 'Опыта нет, курс не является коммерческим опытом.'),
            ('Оркестрация задач', 'Желательно знание Airflow.', False, 'unknown', [],
             'В резюме об этом ничего не сказано.'),
        ], conditions=[{'kind': 'work_mode', 'state': 'conflict',
                        'cv': {'fact_id': 'f6', 'quote': 'только удалённую работу'},
                        'vacancy_quote': 'Работа в офисе.', 'note': 'Удалённо против офиса.'}]),
    ])


def case(fixture, *, personal, min_facts, min_requirements, order, recommendation_in, statuses, mandatory,
         conflicts, expected, known_blocker=None, known_leak=(), rationale=''):
    return {'case_id': fixture['case_id'], 'fixture': fixture['case_id'].removeprefix('E13-'),
            'domain': fixture['domain'], 'split': 'dev', 'decision_status': 'draft', 'rationale': rationale,
            'personal': list(personal), 'min_facts': min_facts, 'min_requirements': min_requirements,
            'passthrough': {'order': order, 'recommendation_in': recommendation_in, 'statuses': statuses,
                            'mandatory': mandatory, 'conflicts': conflicts},
            'real_privacy': {'expected': expected, 'known_blocker': known_blocker, 'known_leak': list(known_leak)}}


DONE = {'processed': None, 'stopped_at': None}


def main():
    cases = [
        case(minimal(), personal=['Орлова', 'Ксения', 'Павловна', '900) 000-00-01', 'ksenia.synthetic@example.com'],
             min_facts=6, min_requirements=2, order=[['job-a', 'job-b']], recommendation_in=['clarify'],
             statuses={'job-a': {'Желателен опыт работы с Python.': ['fail']},
                       'job-b': {'Желательно знание Airflow.': ['unknown'],
                                 'Обязателен коммерческий опыт разработки на Python от 1 года.': ['fail', 'partial']}},
             mandatory={'job-b': 'violated'}, conflicts={'job-a': [], 'job-b': ['work_mode']},
             expected={'processed': 2, 'stopped_at': None},
             known_blocker={'processed': 0, 'stopped_at': {'stage': 'facts', 'code': 'privacy_residual_findings'}},
             known_leak=['Орлова', 'Ксения', 'Павловна'],
             rationale='Первый минимальный набор: подтверждённый SQL и дашборд против явного отрицания Python; '
                       '«об Airflow ничего не сказано» — unknown, не fail; удалёнка против офиса — конфликт условий, '
                       'не отказ.'),
    ]
    data = {'schema_version': 'e13-cases-0.1', 'decision_status': 'draft',
            'note': 'Ожидания — гипотезы команды: допустимые отношения порядка и статусы, не единственный рейтинг. '
                    'known_blocker и known_leak фиксируют текущее поведение настоящего privacy_core на этих '
                    'вымышленных документах; expected — что должно получаться.',
            'cases': cases}
    EXPECT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('e13-cases.json', [c['case_id'] for c in cases])


if __name__ == '__main__':
    main()
