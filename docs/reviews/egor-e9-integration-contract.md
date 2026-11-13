# E9a — контракт подключения E5/E7/E8 и опасные места

14 ноября 2026, Егор. Задача #20. Ветка `egor/e9-quality-integration` от `codex/cli-integration-consultation` `25b0d33`.

В ветку без правок влиты мои опубликованные PR, чтобы проверить их вместе:
- `egor/e7-comparison` `3b51426`: #17 поверх #14 `1ccbabe` и #8 `dd5862c`;
- `egor/e6-cases` `5da6e81` (#16);
- `egor/e8-handoff` `c5295c2`: #19 поверх #18 `57d3a31`.

Конфликтов нет. Дальше идут коммиты E9 с исправлениями. Можно сливать этот PR вместо шести отдельных или после них: дерево то же плюс E9.

Эталонная сборка — `prototype/tests/e9_wiring.py`. Это тестовый помощник, он показывает точные вызовы. Сам `pipeline.py` принадлежит Codex, я его не меняю.

## Что вызывает pipeline

| Шаг | Вызов | Куда кладётся |
|---|---|---|
| Доказательства | `evidence = check_pair(requirements, facts, evaluation, Source.of('cv', safe_resume), Source.of(jid, text))` — как сейчас | `job.evidence_check` |
| Балл | `score(requirements, evaluation, evidence)` с **исходными** требованиями (маркеры не снимать) | `job.score` |
| Рейтинг | `rank(results, expected_count=len(все вакансии запуска))` | `ranking` |
| Профиль | Задача модели `profile` → `CandidateProfile`; `check_profile(profile, facts, Source.of('cv', safe_resume)).model_dump()` | `report.profile` |
| Условия | Задача `conditions` на вакансию → `Conditions`; `check_conditions(c, facts, cv, Source.of(jid, text)).model_dump()` | `ranking.jobs[].conditions` |
| Сравнение | `compare(report, a, b).model_dump()` по запросу или для соседних мест | ответ `get_report` / `comparison` |
| Очередь | `build_review_queue(report)` при каждом чтении; id стабильны, хранить не нужно | ответ сервиса |
| Решения | Сервис записывает `Decision` с версиями `current_versions(report, job)`; `assess_handoff(report, decisions, jid)` | слой решений рядом с запуском |
| Запуск | `report.run_id` — id запуска из run_store | входит в версию отчёта |

Если модель не дала профиль или условия, поле отсутствует (`None`). V5 тогда показывает «не извлечено». Ошибку пишут в `errors` с `stage='profile'` / `'conditions'`; рейтинг она не ломает.

### Отличия от нынешнего обхода `score_review`

| Сейчас (`pipeline.py:116-127`) | По контракту v2 |
|---|---|
| Снимает `mandatory_quote` у требований со спорным `MandatoryCheck` и вызывает `score(score_requirements, evaluation)` | `score(requirements, evaluation, evidence)`: фильтр обязательности внутри |
| `job.score_review.excluded_mandatory_ids` | `job.score.excluded_mandatory_ids`; поле `score_review` не нужно |
| Спорные строки (`needs_review`) засчитываются в L | Спорные строки не входят в L и `coverage`, учитываются в H: `job.score.disputed_ids` |
| `policy_version = draft-2026-11-12-v1` | `draft-2026-11-13-v2`, плюс `evidence_applied: true` |
| Первое место со спорной строкой могло быть `review_top` | `clarify` |

**Поправку не применять дважды.** Если снять маркеры и одновременно передать `evidence`, числа совпадут, но `excluded_mandatory_ids` станет `[]`. Тогда `presentation.py:34` и `write_report` покажут неприменённый маркер как применённый. Воспроизведение — `HazardTests.test_stripping_markers_and_passing_evidence_hides_the_correction`.

Читатели `score_review` переключаются на `score`:
- `presentation.py:34` (`mandatory_applied_to_score`);
- `pipeline.py:224` (строка в `report.md`);
- UI: `prototype/static/report.js:398` в PR #15 читает только `job.score_review?.excluded_mandatory_ids`. Нужно `job.score.excluded_mandatory_ids ?? job.score_review?.excluded_mandatory_ids ?? []` и показ `job.score.disputed_ids`. Это зона Sol/Вани.

## Формы полей

- **`report.profile`** — `ProfileCheck`:
  - `schema_version: candidate-profile-0.1`;
  - `state: structure_ok | needs_review | invalid`, `meaning`;
  - `findings[]`: `where`, `code`, `severity`, `message`, `context`;
  - `spans{path: Span[]}`;
  - `display{path: str}`.

  Пути: `summary[i]`, `stack[i]`, `last_position.role|domain|period`, `achievements[i].action|result`. V5 читает ровно это.
- **`ranking.jobs[].conditions`** — `ConditionsCheck`:
  - `items[]`: `kind`, `state` (`compatible|conflict|unknown`), `check`, `findings`, `cv_span`, `vacancy_span`;
  - на верхнем уровне: `findings`, `conflicts`, `needs_review`, `has_invalid`.
- **`ranking.jobs[].score`** (v2): `lower`, `upper`, `coverage`, `mandatory`, `disputed_ids`, `excluded_mandatory_ids`, `evidence_applied`, `policy_version`.
- **`Comparison`, `ReviewQueue`, `HandoffAssessment`** — описаны в `egor-e7-comparison.md` и `egor-night-handoff.md`. После E9 к ним добавлены причины очереди `condition_review` и `profile_review` (приоритет 4, закрываются `read_context`).

**Строгая схема.** `Requirements`, `Facts`, `Evaluation`, `RequirementFactors`, `CandidateProfile`, `Conditions` проходят `openai.lib._pydantic.to_strict_json_schema` (SDK 2.54, локально, без API):
- у каждого объекта `additionalProperties: false`;
- все поля обязательны;
- `None` выражен через nullable.

Это проверяет тест `test_model_dtos_pass_the_sdk_strict_conversion`. Принимает ли API ограничения длины (`minLength`/`maxItems`), локально не проверить; на текущих `Requirements` они уже работают в live.

## Версии и инварианты

| Что | Версия |
|---|---|
| Политика оценки | `draft-2026-11-13-v2` |
| Профиль | `candidate-profile-0.1` |
| Очередь | `review-queue-0.1` |
| Версия отчёта для решений | `report_sha256`: `run_id`, хеш резюме, факты, ошибки, необработанные, сводка защиты, профиль и по вакансиям требования, оценка, evidence, балл, черновик списка, условия. Без E4-проверки, `verification`, `presentation`, `events`, `usage` |

Инварианты, все под тестами:
1. Балл v2 воспроизводится сравнением E7 на любом подключённом отчёте.
2. Спорная строка не входит в L, спорный `fail` не даёт `violated`.
3. `unknown` после любого решения остаётся `unknown`. Решения не меняют `evaluation`.
4. Список требований считается подтверждённым только по решению `confirm_requirements`. Поле в отчёте не доверяется.
5. Решение относится к одной версии отчёта и одному запуску.
6. Неполный запуск: рекомендация `incomplete`, все передачи `blocked`, у сравнения оговорка.

## Fixtures

`evaluation/expectations/egor/e9-contract-{normal,disputed,incomplete}.json`, генератор `make_e9_contract.py`. В каждом файле отчёт настоящего pipeline, подключённый эталонной сборкой, и производные данные: сравнения соседних мест, очередь, состояние передачи без решений.

| Сценарий | Рекомендация | Ключевое |
|---|---|---|
| normal | `review_top` | Профиль `structure_ok`, `mandatory_fail` у job-003, без блокеров |
| disputed | `clarify` | Неоднозначная цитата → блокер; маркер не того требования → `excluded_mandatory_ids=[r1]`; конфликт формата; зарплата на сверку; «SQL 5 лет» из «SQL 2 года.» → профиль `invalid` и `profile_review` |
| incomplete | `incomplete` | job-002 не прошла проверку цитат; все передачи `blocked`; у сравнения оговорка `incomplete_run` |

## Дефекты, найденные на объединённом коде (исправлены, есть регрессии)

| # | Где | Воспроизведение | Влияние | Исправление |
|---|---|---|---|---|
| D1 | `review_policy.py`, `review_queue.py` | Вписать в отчёт `requirements_review.state='confirmed'`, дать одно решение `mark_for_handoff` | `reviewed_for_handoff` без подтверждения списка; очередь пуста | Подтверждение только решением; очередь всегда показывает список, пока его не подтвердили (`test_hand_written_confirmed_field_confirms_nothing`) |
| D2 | `review_policy.report_sha256` | Два replay-прогона с одинаковым анализом | Решения одного запуска засчитываются в другом | `run_id` входит в версию (`test_decisions_do_not_cross_runs`) |
| D3 | `review_policy.report_sha256` | Изменить `report.profile` после решения «профиль прочитан» | Решение пережило бы изменение того, что видит менеджер | `profile` входит в версию (`test_profile_change_makes_profile_decisions_stale`) |
| D4 | `review_queue.py` | Профиль `invalid` / зарплата `needs_review` без конфликта | В очереди ничего: передача без сверки | Причины `profile_review`, `condition_review` |

## Что структурная проверка не ловит

Это проверяет E9b-раннер на E6.

- **Отрицание и обучение целым предложением.** «Не работал с Python.» или «Изучал Python на курсах.» целиком плюс `full` проходят E3 как `structure_ok`: цитата равна предложению и связана общим термином. Однословная цитата ловится (`quote_is_fragment`), целое предложение — нет. Словарь отрицаний ТЗ запрещает. Ловит это E6 (FE-02, FA-05: допустим только `fail`).
- **Пересекающиеся сроки и стаж** — вывод модели. E6 FA-02 и FE-06 запрещают `full` за счёт сложения.
- **Несоответствие и отсутствие данных.** Политика их различает, но если модель поставит `fail` без факта против, это отклонит `validate_pair` (`missing_evidence`). Если она поставит `fail` с нерелевантным фактом, сработает `evidence_not_linked` → спорная строка → не `violated`.

## Что проверить интегратору на общем SHA

1. Оба replay и неполный сценарий проходят `e9_wiring`-эквивалент в pipeline. `compare` не выдаёт `score_not_reproducible`.
2. В `report.md` и UI спорные строки и неприменённые маркеры показываются из `score`, а не из `score_review`.
3. `run_id` есть в отчёте. Решения сервис пишет с `current_versions`, клиенту запись не доверяется.

## Проверки

```sh
python -m unittest discover -s prototype/tests   # 261 OK (skipped=4)
python -m unittest discover -s tests             # 10 OK
python scripts/check_repository.py               # PASS
python -m prototype demo; python -m prototype demo --scenario disputed
python evaluation/expectations/egor/make_e9_contract.py   # те же fixtures
```
