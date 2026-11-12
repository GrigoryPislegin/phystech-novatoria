from datetime import UTC, datetime
from textwrap import dedent
from typing import final

from hharon.usecases.resume_formatter.experience_formatter import MONTHS_RU, ExperienceFormatter
from hharon.usecases.resume_formatter.resume_formatter import ResumeFormatter


@final
class ObjectDict:
    def __init__(self, data: dict[str, object]):
        self.__data__ = data

    def __getattr__(self, name: str) -> object:
        item = self.__data__[name]
        if isinstance(item, dict):
            return ObjectDict(item)  # pyright: ignore[reportUnknownArgumentType]
        if isinstance(item, list):
            return [ObjectDict(item) if isinstance(item, dict) else item for item in item]  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]

        return item


def test_format_resume_with_complete_data() -> None:
    formatter = ResumeFormatter(experience_formatter=ExperienceFormatter())

    __roga_and_kopita_start = datetime.now(UTC).replace(year=2021)
    __roga_and_kopita_month = MONTHS_RU[__roga_and_kopita_start.month]
    __roga_and_kopita_years = int((datetime.now(UTC) - __roga_and_kopita_start).days // 365)

    resume = ObjectDict({
        "first_name": "Иван",
        "last_name": "Иванов",
        "middle_name": None,
        "area": {"name": "Москва"},
        "gender": {"id": "male"},
        "age": 31,
        "title": "Разработчик Python",
        "total_experience": {
            "months": 120,
        },
        "experience": [
            {
                "company": 'ООО "Рога и Копыта"',
                "start": __roga_and_kopita_start.strftime("%Y-%m-%d"),
                "end": None,
                "position": "Директор",
                "description": "Покупал рога и копыта и продавал по-дороже",
                "area": {"name": "Москва"},
            },
            {
                "company": 'ООО "Месим и варим"',
                "start": "2015-01-01",
                "end": "2019-12-31",
                "position": "Повар",
                "description": "Варил пельмени",
                "area": None,
            },
        ],
        "skill_set": ["Python", "Django", "Flask"],
        "skills": "Я люблю программировать и ездить на машине",
        "driver_license_types": [{"id": "A"}, {"id": "B"}],
        "language": [
            {"name": "Русский", "level": {"name": "Начальный"}},
            {"name": "Английский", "level": {"name": "Продвинутый"}},
        ],
        "education": {
            "level": {
                "name": "Высшее",
            },
            "primary": [
                {
                    "education_level": {"name": "Бакалавриат"},
                    "name": "Университет ИТМО",
                    "organization": "Факультет Информатики и вычислительной техники",
                    "year": 2026.0,
                },
                {
                    "name": "Пермский государственный технический университет",
                    "organization": None,
                    "education_level": None,
                    "year": 2030.0,
                },
            ],
            "elementary": [
                {
                    "name": "Средняя общеобразовательная школа №1",
                    "year": 2022.0,
                }
            ],
            "additional": [
                {
                    "name": "Data Science",
                    "year": 2023.0,
                    "organization": "GeekBrains",
                },
                {
                    "name": "Информационные технологии в системе Федерального казначейства",
                    "year": 2007.0,
                    "organization": "ГОУ ВПО МГТУ имени Н.Э.Баумана",
                },
            ],
            "attestation": [
                {
                    "name": "Приминение и администрирование продуктов ОКБ САПР семейства Аккорд",
                    "year": 2018.0,
                }
            ],
        },
    })

    expected = dedent(
        f"""\
        **Иван Иванов**
        Москва, Мужчина, 31 год

        **Разработчик Python**
        Общий опыт работы: 10 лет


        **Директор в компании ООО "Рога и Копыта"**, Москва
        *{__roga_and_kopita_month} {__roga_and_kopita_start.year} — настоящее время, {__roga_and_kopita_years} лет*

        Покупал рога и копыта и продавал по-дороже

        **Повар в компании ООО "Месим и варим"**
        *Январь 2015 — Декабрь 2019, 5 лет*

        Варил пельмени


        **Ключевые навыки**
        Python, Django, Flask

        **Водительские права**
        Категории: A, B

        **Образование**
        Уровень: Высшее
        - **Университет ИТМО**, 2026, *Факультет Информатики и вычислительной техники*
        - **Пермский государственный технический университет**, 2030
        - **Средняя общеобразовательная школа №1**, 2022

        **Курсы повышения квалификации**
        - "Data Science", GeekBrains, 2023
        - "Информационные технологии в системе Федерального казначейства", ГОУ ВПО МГТУ имени Н.Э.Баумана, 2007

        **Сертификаты**
        - Приминение и администрирование продуктов ОКБ САПР семейства Аккорд, 2018

        **Языки**
        - Английский — Продвинутый
        - Русский — Начальный

        **Обо мне**
        Я люблю программировать и ездить на машине
        """
    )

    result = formatter.format_resume(resume)  # pyright: ignore[reportArgumentType]
    assert expected == result
