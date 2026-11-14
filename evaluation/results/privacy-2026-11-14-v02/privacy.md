# Privacy acceptance — синтетический корпус

Режим: `real_local_ner_on_synthetic`; оценено 21/21 случаев.
Не измеряет анонимность, recall реальных резюме или качество модели подбора.

| Метрика | Успешно / оценено | Ожидалось | Не измерено |
|---|---:|---:|---:|
| identifiers_masked | 19/19 | 19 | 0 |
| professional_preserved | 24/28 | 28 | 0 |

## ru_name_city — assessed


| Роль | Ожидаемый фрагмент | [start, end) | Результат |
|---|---|---|---|
| identifier | Мария Петрова | [0, 13) | masked |
| identifier | Москва | [14, 20) | masked |
| professional | Разрабатывала на Python 3 года. | [21, 52) | preserved |

Найденные фрагменты: PERSON[0:13]='Мария Петрова'; LOCATION[14:20]='Москва'

## contacts — assessed


| Роль | Ожидаемый фрагмент | [start, end) | Результат |
|---|---|---|---|
| identifier | candidate.synthetic@example.org | [7, 38) | masked |
| identifier | +7 (999) 123-45-67 | [48, 66) | masked |
| professional | Python, SQL | [75, 86) | preserved |

Найденные фрагменты: EMAIL[7:38]='candidate.synthetic@example.org'; PHONE[48:66]='+7 (999) 123-45-67'; CONTACT[7:38]='candidate.synthetic@example.org'

## obfuscated_email — assessed


| Роль | Ожидаемый фрагмент | [start, end) | Результат |
|---|---|---|---|
| identifier | resume [at] example [dot] org | [9, 38) | masked |
| professional | SQL 2 года | [44, 54) | preserved |

Найденные фрагменты: EMAIL[9:38]='resume [at] example [dot] org'

## unicode_email — assessed


| Роль | Ожидаемый фрагмент | [start, end) | Результат |
|---|---|---|---|
| identifier | synthetic@example.org | [7, 28) | masked |
| professional | Java 3 года | [43, 54) | preserved |

Найденные фрагменты: EMAIL[7:28]='synthetic@example.org'; CONTACT[7:28]='synthetic@example.org'

## handles_links — assessed


| Роль | Ожидаемый фрагмент | [start, end) | Результат |
|---|---|---|---|
| identifier | fictive_person | [11, 25) | masked |
| identifier | linkedin.com/in/fictive-person | [36, 66) | masked |
| professional | Python | [75, 81) | preserved |

Найденные фрагменты: LINK[36:66]='linkedin.com/in/fictive-person'; LINK[36:66]='linkedin.com/in/fictive-person'; CONTACT[11:25]='fictive_person'; CONTACT[36:66]='linkedin.com/in/fictive-person'; ORG[0:8]='Telegram'; ORG[26:34]='LinkedIn'

## ru_address — assessed


| Роль | Ожидаемый фрагмент | [start, end) | Результат |
|---|---|---|---|
| identifier | ул. Лесная, д. 12, кв. 45 | [8, 33) | masked |
| professional | SQL 3 года | [40, 50) | preserved |

Найденные фрагменты: IDENTITY[8:33]='ул. Лесная, д. 12, кв. 45'

## birthdate — assessed


| Роль | Ожидаемый фрагмент | [start, end) | Результат |
|---|---|---|---|
| identifier | 31 декабря 1990 | [15, 30) | masked |
| professional | Python 3 года | [39, 52) | preserved |

Найденные фрагменты: IDENTITY[15:30]='31 декабря 1990'

## english_header — assessed


| Роль | Ожидаемый фрагмент | [start, end) | Результат |
|---|---|---|---|
| identifier | John Smith | [0, 10) | masked |
| professional | Python for 4 years | [23, 41) | preserved |

Найденные фрагменты: PERSON[0:10]='John Smith'

## english_labels — assessed


| Роль | Ожидаемый фрагмент | [start, end) | Результат |
|---|---|---|---|
| identifier | John Smith | [11, 21) | masked |
| identifier | London, Baker Street 22 | [31, 54) | masked |
| professional | SQL: 3 years | [55, 67) | preserved |

Найденные фрагменты: IDENTITY[11:21]='John Smith'; IDENTITY[31:54]='London, Baker Street 22'

## english_prose — assessed

Известное ограничение (остаётся в знаменателе): English personal names embedded in prose are not guaranteed by Russian news NER.

| Роль | Ожидаемый фрагмент | [start, end) | Результат |
|---|---|---|---|
| identifier | John Smith | [11, 21) | masked |
| professional | develop software using Python | [25, 54) | preserved |

Найденные фрагменты: PERSON[11:21]='John Smith'

## skills_negation — assessed


| Роль | Ожидаемый фрагмент | [start, end) | Результат |
|---|---|---|---|
| professional | Python 3 года | [16, 29) | preserved |
| professional | SQL 1 год | [43, 52) | preserved |
| professional | Не работал с Java | [54, 71) | preserved |

Найденные фрагменты: нет

## rust_resume — assessed

Известное ограничение (остаётся в знаменателе): Known Rust mismatch: resume context may mask skill as ORG.

| Роль | Ожидаемый фрагмент | [start, end) | Результат |
|---|---|---|---|
| professional | Go | [12, 14) | preserved |
| professional | Rust | [17, 21) | removed |

Найденные фрагменты: ORG[17:21]='Rust'

## rust_vacancy — assessed

Известное ограничение (остаётся в знаменателе): Paired context control for rust_resume; preserve the same professional skill.

| Роль | Ожидаемый фрагмент | [start, end) | Результат |
|---|---|---|---|
| professional | Rust | [17, 21) | preserved |

Найденные фрагменты: нет

## sql_contractor — assessed

Известное ограничение (остаётся в знаменателе): Conservative company/contractor control; do not fix skill loss using a blanket technology allowlist.

| Роль | Ожидаемый фрагмент | [start, end) | Результат |
|---|---|---|---|
| identifier | SQL | [11, 14) | masked |
| professional | 1 год как с подрядчиком | [15, 38) | preserved |

Найденные фрагменты: ORG[11:14]='SQL'

## excel_employer — assessed

Известное ограничение (остаётся в знаменателе): Company-context control paired with excel_skill.

| Роль | Ожидаемый фрагмент | [start, end) | Результат |
|---|---|---|---|
| identifier | Excel | [19, 24) | masked |
| professional | работала бухгалтером | [30, 50) | preserved |

Найденные фрагменты: ORG[19:24]='Excel'

## excel_skill — assessed


| Роль | Ожидаемый фрагмент | [start, end) | Результат |
|---|---|---|---|
| professional | Excel | [10, 15) | preserved |
| professional | составления таблиц | [20, 38) | preserved |

Найденные фрагменты: нет

## english_job_title — assessed

Известное ограничение (остаётся в знаменателе): Conservative English name-header rule may mask a professional heading.

| Роль | Ожидаемый фрагмент | [start, end) | Результат |
|---|---|---|---|
| professional | Senior Python Developer | [0, 23) | removed |
| professional | Commercial experience: 4 years | [24, 54) | preserved |

Найденные фрагменты: PERSON[0:23]='Senior Python Developer'

## employment_dates — assessed

Известное ограничение (остаётся в знаменателе): Full dates may be masked even when they describe professional experience.

| Роль | Ожидаемый фрагмент | [start, end) | Результат |
|---|---|---|---|
| professional | 2020-01-01 | [10, 20) | removed |
| professional | 2023-12-31 | [24, 34) | removed |
| professional | Разрабатывал на Python | [36, 58) | preserved |

Найденные фрагменты: DATE[10:20]='2020-01-01'; DATE[24:34]='2023-12-31'

## english_middle_initial — assessed


| Роль | Ожидаемый фрагмент | [start, end) | Результат |
|---|---|---|---|
| identifier | John A. Smith | [11, 24) | masked |
| professional | I develop software using Python. | [26, 58) | preserved |

Найденные фрагменты: PERSON[11:24]='John A. Smith'

## english_initials — assessed


| Роль | Ожидаемый фрагмент | [start, end) | Результат |
|---|---|---|---|
| identifier | J. R. Smith | [11, 22) | masked |
| professional | I develop software using Python. | [24, 56) | preserved |

Найденные фрагменты: PERSON[11:22]='J. R. Smith'

## english_conjunction — assessed


| Роль | Ожидаемый фрагмент | [start, end) | Результат |
|---|---|---|---|
| identifier | John Smith | [11, 21) | masked |
| professional | I develop software using Python. | [26, 58) | preserved |

Найденные фрагменты: PERSON[11:21]='John Smith'
