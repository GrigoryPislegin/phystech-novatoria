# E9 — контракт E5/E7/E8 на интегрированной базе и находки

14 ноября 2026, Егор. Задача #20.

Ветка `egor/e9a-contract` от `codex/cli-integration-consultation` `aeb0429`: интеграция, где pipeline уже подключает мои E5/E7/E8. Она заменяет PR #21 (#21 строился на `25b0d33` до интеграции).

Мои модули в `aeb0429` не менялись. Исправления ниже — только в них, файлы интегратора не правлю.

## Контракт, как он подключён в `aeb0429`

| Шаг | Что делает pipeline | Совпадает с контрактом |
|---|---|---|
| Факты + профиль | Модель возвращает `ResumeAnalysis` (факты + `CandidateProfile`) → `check_profile` → `report.profile` + `report.profile_missing` | да |
| Требования | Как раньше | да |
| Оценка + условия | `VacancyAnalysis` (строки + `Conditions`) → `check_conditions` → `job.conditions` | да |
| Балл | `score(requirements, evaluation, evidence)` с исходными требованиями; `score_review` — копия `score.excluded_mandatory_ids` | да, поправка не применяется дважды |
| Представления | `refresh_derived`: сравнения «первое место против остальных», `review_queue`, `handoff`, `presentation` — после баллов | да |
| `run_id` | Нет: должен поставить run_store, затем вызвать `refresh_derived` | без него передача закрыта (`run_unbound`) |

Строгая схема. `Requirements`, `Facts`, `Evaluation`, `RequirementFactors`, `CandidateProfile`, `Conditions`, `ResumeAnalysis`, `VacancyAnalysis` проходят `openai.lib._pydantic.to_strict_json_schema` (SDK 2.54, локально, без API):
- у объектов `additionalProperties: false`;
- все поля обязательны;
- `None` выражен через nullable.

Принимает ли API ограничения длины, без вызова не проверить.

## Исправлено в моих модулях

У каждого исправления есть регрессия, которая падает на старом поведении.

| # | Где | Воспроизведение | Влияние | Исправление и тест |
|---|---|---|---|---|
| D1 | `review_policy`, `review_queue` | В отчёт вписано `requirements_review.state='confirmed'` + одно решение `mark_for_handoff` | `reviewed_for_handoff` без подтверждения списка, очередь пуста | Подтверждение только решением `confirm_requirements`; очередь показывает список, пока его не подтвердили (`test_hand_written_confirmed_field_confirms_nothing`) |
| D2 | `review_policy.report_sha256` | Два одинаковых replay-прогона | Решения переходили между запусками | `run_id` в версии отчёта (`test_decisions_do_not_cross_runs`) |
| D3 | `review_policy.report_sha256` | Профиль или `profile_missing` изменились после решения | Решение пережило изменение того, что видит менеджер | Оба поля в версии отчёта (`test_profile_or_missing_sections_change_the_version`, `test_profile_and_missing_sections_are_in_the_report_version`) |
| D4 | `review_queue` | Профиль `needs_review`/`invalid`; зарплата `needs_review` без конфликта | Передача без сверки | `profile_review`, `condition_review` (приоритет 4, `read_context`) |
| D5 | `review_queue` | Ошибка на стадии `profile` (`job_id: null`) | Становилась `processing_error`: все передачи навсегда `blocked` | Ошибки читаются по стадии: `profile`/`conditions` → пункт проверки `not_extracted`, не блокер |
| D6 | `review_policy` | Отчёт без `run_id` | Защита D2 не работала | Без `run_id` передача остаётся `draft`, причина `run_unbound` (`test_pipeline_output_without_run_id_is_never_handed_off`) |
| D7 | `review_queue` | Текст `mandatory_fail` | Обещал «исключает вакансию», а движок вакансию понижает | «Опускается в группу с нарушением, но не исключается; решение принимает HR» (`test_mandatory_fail_text_does_not_promise_exclusion`) |

## Находки в файлах интегратора: воспроизведение и патч

`prototype/tests/test_e9_contract.py::IntegrationFindingTests` воспроизводит каждую находку как `expectedFailure`. Проверенный патч — [`egor-e9-pipeline.patch`](egor-e9-pipeline.patch), 53 строки, `git apply --check` проходит. С ним все пять тестов проходят. После применения пометки `expectedFailure` нужно снять: unittest сообщит о «unexpected success».

| # | Приоритет | Где | Воспроизведение | Влияние |
|---|---|---|---|---|
| R1 | P1 | `pipeline.py:122-124` | В `summary` профиля «SQL 5 лет» при факте «SQL 2 года.» | Весь запуск падает на `facts_validation` (`invalid_profile`), 0 вакансий в рейтинге. Профиль в балл не входит, но из-за него теряется весь рейтинг |
| R2 | P1 | `pipeline.py:144-146` | `vacancy_quote` условия не найден в вакансии | Вакансия выпадает из рейтинга, запуск становится неполным, хотя её требования и оценка валидны |
| R3 | P1 | `pipeline.py:278-281` (`report.md`) | Строка `full` со спорной цитатой «Python» (стоит и под «Работал с:», и под «Не работал с:») | «Сильные стороны: Python» в менеджерском выводе. `presentation.manager_brief` это уже исключает, `report.md` — нет |
| R4 | P2 | там же | Строка `fail` со спорным доказательством («SQL 2 года.» против Python) | «Выявленные несоответствия: Python», хотя по политике v2 спорный `fail` не нарушение |
| R5 | P2 | `report.md` | Конфликт «только удалённо» против «работа в офисе» | В `report.md` об условиях ни слова; виден только в JSON/UI |

**Развилка по R1 и R2 решает интегратор.** Тест `test_integrated_analysis.test_forged_profile_fact_is_not_published_as_valid_candidate` сознательно валит весь запуск при подделанной ссылке на факт в профиле: испорченный ответ модели считается признаком недоверия ко всему ответу. Патч делает иначе:
- профиль получает `state: invalid` (V5 показывает «Не удалось проверить профиль»);
- очередь даёт `profile_review`;
- рейтинг остаётся.

Мой довод: профиль не участвует в балле, а цена «потерять рейтинг всех вакансий из-за одного числа в выжимке» выше риска. С патчем этот тест интегратора падает (1 тест). Если оставить нынешнее поведение, R1 и R2 — сознательное решение, тогда снимите эти два теста.

## Fixtures

`evaluation/expectations/egor/e9-contract-{normal,disputed,incomplete}.json`, генератор `make_e9_contract.py`. Источник — настоящий `run_pipeline` с синтетическими моделями в wire-DTO. Генератор ставит `run_id`, как run_store, и вызывает `refresh_derived`.

| Сценарий | Рекомендация | Передача | Ключевое |
|---|---|---|---|
| normal | `review_top` | все `draft` | Профиль `structure_ok`; `mandatory_fail` у job-003 |
| disputed | `clarify` | job-a `blocked`, job-b `draft` | Неоднозначная цитата → блокер; маркер не того требования → `excluded_mandatory_ids=[r1]`; конфликт формата; зарплата на сверку; профиль `needs_review` → `profile_review` |
| incomplete | `incomplete` | все `blocked` | job-002 не прошла проверку цитат; у сравнения оговорка `incomplete_run` |

Тесты сверяют с JSON-отчётом то, что из него строится: очередь, передачу, сравнения, `presentation`. Ожидания по сценариям записаны вручную.

## Что структурная проверка не ловит

Это проверяет E9b-раннер на E6.

- **Отрицание и обучение целым предложением.** «Не работал с Python.» / «Изучал Python на курсах.» + `full` проходят E3 как `structure_ok`. Однословная цитата ловится. Словарь отрицаний ТЗ запрещает. E6 FE-02, FA-05 допускают только `fail`.
- **То же в профиле.** Пункт стека «Python» из факта с отрицанием проходит `check_profile`. Смягчает то, что V5 показывает рядом предложение-источник. E6 профиль не размечает.
- **Пересекающиеся сроки и стаж** — вывод модели. E6 FA-02 и FE-06 запрещают `full` за счёт сложения.

## Что проверить интегратору

1. Применить или отклонить [патч](egor-e9-pipeline.patch) и снять соответствующие `expectedFailure`.
2. run_store: `report.run_id` + `refresh_derived` при публикации; решения записывает сервис с `current_versions`.
3. UI: `prototype/static/report.js` должен брать исключённые маркеры и спорные строки из `job.score`, а не только из `score_review`.

## Проверки

```sh
python -m unittest discover -s prototype/tests   # 287 OK (skipped=4, expected failures=5)
python -m unittest discover -s tests             # 10 OK
python scripts/check_repository.py               # PASS
python -m prototype demo; python -m prototype demo --scenario disputed
python evaluation/expectations/egor/make_e9_contract.py   # те же fixtures
```
