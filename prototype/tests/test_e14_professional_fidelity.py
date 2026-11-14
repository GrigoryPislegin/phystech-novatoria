"""E14: professional meaning must survive the privacy step; personal values must not (real NER only).

Runs where the public NER weights and libraries are installed (the Docker image); elsewhere the
whole module is skipped because there is no detector to test. Where it runs, a lost professional
term or a leaked personal value FAILS: a known defect is never turned into a skip or a green
expectation here. The fragments are fictional examples for checking context; they are not a
proposal for a general allowlist. Nothing is sent anywhere and no model is measured.
"""
import asyncio
import json
import re
import unittest

from prototype.tests.test_e13_support import load_fixture, real_privacy_available, run

REFERENCE = re.compile(r'\[\[PRIV:[a-f0-9]{16}:\d+:[A-Z]+\]\]')

# (text, fragments that must stay readable)
PROFESSIONAL = [
    ('Опыт работы 5 лет.', ['Опыт', '5 лет']),
    ('Full Stack Developer, 4 года коммерческой разработки.', ['Full Stack Developer', '4 года']),
    ('Стек: Vue.js, TypeScript, SQL, Git, Figma.', ['Vue.js', 'TypeScript', 'SQL', 'Git', 'Figma']),
    ('Навыки:\n- Vue.js\n- TypeScript\n- REST API\n- Git\n- Figma', ['Vue.js', 'TypeScript', 'REST API', 'Git', 'Figma']),
    ('Проектировал REST API на Node.js.', ['REST API', 'Node.js']),
    ('Работал с PostgreSQL, Docker и Kafka.', ['PostgreSQL', 'Docker', 'Kafka']),
    ('Строил дашборды в Power BI и Tableau.', ['Power BI', 'Tableau']),
    ('Вёл учёт в 1С:Бухгалтерия и Excel, знаю МСФО.', ['1С:Бухгалтерия', 'Excel', 'МСФО']),
    ('С TypeScript не работал.', ['TypeScript', 'не работал']),  # negation
    ('2021–2024 — frontend-разработчик, интернет-магазин.', ['2021–2024', 'frontend-разработчик']),  # dates, role
    ('Обязателен опыт работы с Vue.js от 2 лет.', ['Обязателен', 'Vue.js', 'от 2 лет']),  # obligatoriness, units
    ('Сократил время загрузки страницы с 4 до 1,5 секунды.', ['Сократил', 'с 4 до 1,5 секунды']),  # achievement
    ('Формат работы: удалённо, зарплата до 250 000 рублей в месяц.', ['удалённо', '250 000 рублей']),  # conditions
    ('Английский язык — B2.', ['Английский', 'B2']),
]

# (text, personal values that must be hidden, professional fragments of the same text that must stay)
PERSONAL = [
    ('Ковалёв Артём Игоревич\nFull Stack Developer', ['Ковалёв', 'Артём', 'Игоревич'], ['Full Stack Developer']),
    ('Телефон: +7 (900) 000-00-05, email: artem.synthetic@example.com',
     ['900) 000-00-05', 'artem.synthetic@example.com'], []),
    ('Telegram: @artem_synthetic, github.com/artem-synthetic', ['artem_synthetic', 'artem-synthetic'], []),
    ('2021–2024 — разработчик, ООО «Тихая Гавань», работал с Vue.js.', ['Тихая Гавань'],
     ['Vue.js', '2021–2024', 'разработчик']),  # a private employer next to a tool
    ('Работал в команде Марины Соколовой над проектом на TypeScript.', ['Марины', 'Соколовой'], ['TypeScript']),
    ('Руководитель: Зульфия Хабибуллина. Стек: SQL, Git.', ['Зульфия', 'Хабибуллина'], ['SQL', 'Git']),  # rare name
    ('Проживаю: Казань, ул. Лесная, д. 12.', ['Лесная', 'д. 12'], []),
]


def redact_all(texts):
    from prototype.privacy import local_privacy

    async def go():
        async with local_privacy() as privacy:
            return [await privacy.redact(text) for text in texts]
    return asyncio.run(go())


@unittest.skipUnless(real_privacy_available(), 'no NER detector here: public weights or libraries are not installed')
class FragmentTests(unittest.TestCase):
    def test_professional_fragments_stay_readable(self):
        safe = redact_all([text for text, _ in PROFESSIONAL])
        lost = {text: [k for k in keep if k not in out] for (text, keep), out in zip(PROFESSIONAL, safe)}
        lost = {text: terms for text, terms in lost.items() if terms}
        kept = sum(len(keep) for _, keep in PROFESSIONAL) - sum(map(len, lost.values()))
        self.assertEqual(lost, {}, f'professional fragments kept: {kept} of {sum(len(k) for _, k in PROFESSIONAL)}')

    def test_personal_values_are_hidden(self):
        safe = redact_all([text for text, _, _ in PERSONAL])
        leaked = {text: [h for h in hide if h in out] for (text, hide, _), out in zip(PERSONAL, safe)}
        self.assertEqual({t: v for t, v in leaked.items() if v}, {})

    def test_professional_text_next_to_personal_data_stays_readable(self):
        safe = redact_all([text for text, _, _ in PERSONAL])
        lost = {text: [k for k in keep if k not in out] for (text, _, keep), out in zip(PERSONAL, safe)}
        self.assertEqual({t: v for t, v in lost.items() if v}, {})


@unittest.skipUnless(real_privacy_available(), 'no NER detector here: public weights or libraries are not installed')
class EndToEndFidelityTests(unittest.TestCase):
    """Real NER + SDK MockTransport + pipeline on the E13 analytics set. Counting processed vacancies
    is not enough: a run that reaches 3 of 3 by destroying the terms fails the quality criterion."""

    # Tools and markers a recruiter needs to read in the documents of this fictional set.
    RESUME_TERMS = ['SQL', 'ClickHouse', 'PostgreSQL', 'Excel', 'A/B-тестов', 'Python', 'pandas', 'Tableau',
                    'Amplitude', 'Airflow', 'Spark', 'B2', '2021 — по настоящее время', 'с 3,1% до 3,8%',
                    'не работал', 'только удалённую работу', 'от 250 000 рублей']
    VACANCY_TERMS = {'an-1': ['SQL', 'A/B-тестов', 'Python', 'Tableau', 'Amplitude', 'ML-моделей', 'от 3 лет'],
                     'an-2': ['Airflow', 'Spark', 'SQL', 'Python', 'ClickHouse', 'Kafka', 'Docker', 'от 2 лет'],
                     'an-3': ['SQL', 'Power BI', 'Tableau', 'DAX', 'Excel', 'Python', 'от 2 лет']}
    PERSONAL = ['Зуев', 'Тимур', 'Ренатович', '900) 000-00-03', 'timur.synthetic@example.com']

    @classmethod
    def setUpClass(cls):
        cls.fixture = load_fixture('analytics')
        cls.report, cls.replay = run(cls.fixture, privacy='local')
        cls.sent = {}  # task/job -> the processed text the model was shown
        for (task, job_id), body in zip(cls.replay.requests, cls.replay.outbound):
            data = json.loads(json.loads(body)['input'][1]['content'])['data']
            cls.sent[(task, job_id)] = data.get('text') or data.get('vacancy_text') or ''

    def test_no_personal_value_is_sent(self):
        everything = '\n'.join(self.replay.outbound)
        self.assertEqual([v for v in self.PERSONAL if v in everything], [])

    def test_every_vacancy_is_processed(self):
        self.assertEqual((len(self.report['ranking']['jobs']), self.report['errors']), (3, []))

    def test_resume_terms_reach_the_model(self):
        shown = self.sent.get(('facts', None), '')
        lost = [t for t in self.RESUME_TERMS if t not in shown]
        self.assertEqual(lost, [], f'resume terms kept: {len(self.RESUME_TERMS) - len(lost)} of {len(self.RESUME_TERMS)}')

    def test_vacancy_terms_reach_the_model(self):
        lost = {job: [t for t in terms if t not in self.sent.get(('requirements', job), '')]
                for job, terms in self.VACANCY_TERMS.items()}
        self.assertEqual({j: t for j, t in lost.items() if t}, {})

    def test_requirements_stay_distinguishable(self):
        # Two different requirements must not turn into the same masked line.
        for job in self.report['ranking']['jobs']:
            masked = [REFERENCE.sub('▮', r['quote']) for r in job['requirements']['items']]
            repeated = sorted({q for q in masked if masked.count(q) > 1})
            self.assertEqual(repeated, [], job['job_id'])

    def test_counted_evidence_is_readable(self):
        # A row that enters the lower bound must cite text a recruiter can read, not only a mask.
        facts = {f['id']: f['quote'] for f in self.report['facts']['items']}
        unreadable = []
        for job in self.report['ranking']['jobs']:
            counted = set(job['score']['breakdown']['full']) | set(job['score']['breakdown']['partial'])
            for row in job['evaluation']['rows']:
                if row['requirement_id'] in counted:
                    for fact_id in row['fact_ids']:
                        if not re.search(r'[A-Za-zА-Яа-яЁё]{3}', REFERENCE.sub('', facts[fact_id])):
                            unreadable.append((job['job_id'], row['requirement_id'], fact_id))
        self.assertEqual(unreadable, [])


if __name__ == '__main__':
    unittest.main()
