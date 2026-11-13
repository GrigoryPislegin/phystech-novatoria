# Ночной handoff Егора — E8: очередь проверки и решения рекрутера

13–14 ноября 2026. Задача #9.

**E8a** (этот PR): ветка `egor/e8-review-queue` от `codex/cli-integration-consultation` (`ca73178`). В ней DTO, очередь, два fixture и контракт `assess_handoff`.
**E8b**: ветка `egor/e8-handoff` поверх E8a. В ней решения рекрутера и `assess_handoff`.

На этой базе балл считается по `draft-2026-11-12-v1` с фильтром обязательности Codex, и fixtures записаны на ней. Очередь читает поля этой базы (`evidence_check`, `score_review`, `requirements_review`, `requirements_draft`, `privacy`). Если появятся поля v2 из PR #14 (`score.disputed_ids`, `score.excluded_mandatory_ids`), она читает и их. Ожидания и приоритеты — решение команды, не ответы эксперта.

## `build_review_queue(report) -> ReviewQueue`

Чистая функция в `prototype/review_queue.py`:
- не вызывает модель, не читает файлов и не меняет отчёт;
- в pipeline не подключена (`INTEGRATED = False`).

Пункт очереди (`ReviewItem`):

| Поле | Смысл |
|---|---|
| `id` | 16 hex из sha256 от хешей обработанного резюме и вакансии, `job_id`, `requirement_id` или `condition_kind` и `reason_code`. Для пунктов запуска вместо хеша вакансии берутся хеши всех вакансий и id необработанных. Не зависит от порядка вакансий и файлов. Один сигнал — один пункт |
| `job_id`, `requirement_id`, `condition_kind` | `None` у пунктов уровня запуска и вакансии. Условия E5 идут в `condition_kind` и с id требований модели не смешиваются |
| `reason_code`, `kind`, `priority`, `action`, `explanation` | Из таблицы ниже |
| `refs` | Цитаты из отчёта. Резюме: span E3 с предложением и заголовком; если span нет, цитата факта без предложения. Вакансия: цитата требования, маркер с предложением, span условия E5. Отсутствующее не достраивается |
| `contexts` | Разные контексты неоднозначной цитаты или непокрытые предложения вакансии |
| `detail_codes` | Исходные коды E3, E4, E5 |

`ReviewQueue` хранит `items`, отсортированные по приоритету, вакансии, требованию и причине. Ещё в нём:
- `by_reason`, `by_job` (`''` — уровень запуска), `by_priority`;
- `policy_version`;
- `model_status: model_proposed` — статусы остаются предложениями модели, попали они в очередь или нет.

Никаких заявлений о точности или сэкономленном времени.

### Причины → действия

| Приоритет | Причина | Вид | Действие | Сигнал в отчёте |
|---|---|---|---|---|
| 1 | `processing_error` | integrity | `complete_run` | `unprocessed[]`, `errors[]` без `job_id` |
| 1 | `incomplete_run` | integrity | `complete_run` | `ranking.complete = false` |
| 1 | `invalid_evidence` | integrity | `fix_source` | E3 row/mandatory `invalid`, E5 condition `invalid` |
| 1 | `ambiguous_location` | integrity | `read_context` | E3 `ambiguous_location`: цитата в разных контекстах, например «Работал с:» и «Не работал с:» |
| 1 | `requirements_stale` | integrity | `check_list` | E4 `stale`/`invalid` или проверка чужой вакансии |
| 2 | `mandatory_unbound` | interpretation | `check_list` | `MandatoryCheck.needs_review` или маркер исключён из балла |
| 2 | `disputed_negative` | interpretation | `read_context` | E3 `needs_review` (или v2 `disputed_ids`) у строки `fail` |
| 2 | `mandatory_fail` | interpretation | `read_context` | `fail` по применённому обязательному без спора, в том числе без проверки E3 (`evidence_not_checked`): именно эта строка исключает вакансию |
| 2 | `privacy_may_hide` | missing_info | `compare_with_original` | `privacy.professional_information_may_be_hidden` |
| 3 | `condition_conflict` | conditions | `decide_condition` | E5 `conflict` или `unknown_with_both_sides` в `job.conditions`, а также `conflicts[]` верхнего уровня. Неразборчивая запись даёт `invalid_evidence` и не пропадает |
| 4 | `mandatory_unknown` | missing_info | `ask_candidate` | `unknown` по применённому обязательному |
| 4 | `disputed_evidence` | interpretation | `read_context` | E3 `needs_review` у строки `full`/`partial`, в том числе обязательной: пункт списка под заголовком, часть предложения |
| 4 | `requirements_unconfirmed` | requirements | `check_list` | E4 не `confirmed` |
| 4 | `uncovered_text` | requirements | `check_list` | E4 `uncovered` |

Внутри приоритета порядок детерминирован, но важность для найма он не выражает.
- Нормальная строка со `structure_ok` в очередь не попадает: недоказанность смысла уже отражена в общем `model_proposed`.
- Спорный `full` (например, «Навыки:\n- Python») идёт в приоритет 4, а не 2: это не отрицательный вывод.
- Строка или проверка с id требования, которого нет в списке, даёт `invalid_evidence`, а не падение.

### Fixtures

Генератор — `evaluation/expectations/egor/make_e8_fixtures.py`: он строит отчёты настоящим pipeline с синтетической моделью и удаляет `events`.

- **`e8-queue-normal.json`** — demo success. Пять пунктов: `mandatory_fail` (job-003, SQL 1 год против 3), `mandatory_unknown` (job-002, Java) и три `requirements_unconfirmed`. Срочных пунктов по целостности и условиям нет.
- **`e8-queue-disputed.json`** — 12 пунктов:
  - «Работал с: Python» / «Не работал с: Python» → `ambiguous_location`;
  - «Обязательно: Go. Python желателен.» с маркером на Python → `mandatory_unbound` и `disputed_negative`;
  - Rust при защите данных → `mandatory_unknown` и `privacy_may_hide`, а не `fail`;
  - необработанная `job-d` → `processing_error`, `incomplete_run`, рекомендация `incomplete`;
  - «только удалённо» против «работа в офисе» → `condition_conflict` и `uncovered_text`.

  Поле `job.conditions` подложено вручную в форме E5 `ConditionsCheck` из PR #8, потому что `candidate_profile` на этой базе ещё нет. Спаны получены настоящим `locate` по тем же текстам. `job.conditions` — предлагаемое имя поля для Codex. После подключения E5 fixture нужно пересобрать через `check_conditions`.

## E8b: `assess_handoff(report, decisions, job_id) -> HandoffAssessment`

Чистая функция в `prototype/review_policy.py`:
- ничего не пишет и не меняет оценку модели;
- в pipeline и сервис не подключена (`INTEGRATED = False`).

- **`report_sha256(report)`** — версия **анализа**: хеш резюме, факты, ошибки, сводка защиты и по каждой вакансии требования, оценка, доказательства, балл, черновик списка, условия. Порядок вакансий не важен. Слой проверки сюда не входит: E4 `requirements_review`, `verification`, `presentation`, `events`, `usage`. Поэтому запись решения или подтверждения не делает другие решения устаревшими.
- **`current_versions(report, job)`** — набор версий, который сервис записывает в решение.
- **`closing_decision(reason)`** — какое решение закрывает пункт; `None` у блокеров.

`Decision` — действие человека, которое записал сервис. Произвольный JSON клиента или текст модели решением не считаются.

```text
decision_id, job_id, item_id | None
action: confirm_requirements | read_context | accept_condition | mark_for_handoff
report_sha256, resume_sha256, source_sha256, requirements_sha256, policy_version   # версия решения
decided_by: 'recruiter', recorded_by: 'service', decided_at
```

`HandoffAssessment`:

```text
job_id
state: draft | reviewed_for_handoff | blocked | stale | invalid
model_status: 'model_proposed'   # решения не меняют статусы оценки
requirements_confirmed           # E4 'confirmed' в отчёте или валидное confirm_requirements
processing_complete              # все вакансии обработаны; о смысле строк ничего не говорит
blockers[]            # пункты, которые решением не закрываются
open_items[]          # пункты без нужного решения
acknowledged[]        # прочитанные пункты; статусы не меняются (unknown остаётся unknown)
accepted_exceptions[] # конфликты условий, принятые HR; остаются видимыми
reasons[]             # коды: stale_<версия>, unknown_item, foreign_job, duplicate_decision,
                      # not_a_service_decision, missing_item, blocker_not_closable, wrong_action,
                      # marked_with_open_items, marked_without_confirmed_list
```

Правила:
1. **`reviewed_for_handoff`** требует: явного `mark_for_handoff` на текущих версиях, отсутствия блокеров и ни одного открытого пункта. Неподтверждённый список — тоже открытый пункт, его закрывает только `confirm_requirements`. Подтверждение списка и решение о передаче — разные действия. Пункты уровня запуска (`privacy_may_hide`, `incomplete_run`) входят в оценку каждой вакансии.
   - Чем закрывается пункт — в таблице ниже. Лишнее действие на пункте даёт `wrong_action`, но уже сделанное нужное действие не отменяет. Порядок решений не важен.
   - Порядок состояний: `invalid` → `blocked` → `reviewed_for_handoff` → `stale` → `draft`.
2. **Блокеры.** `processing_error`, `incomplete_run`, `invalid_evidence`, `ambiguous_location` и `requirements_stale` кнопкой не закрываются. Неполный запуск не даёт окончательного общего рейтинга.
3. **Версии.** Решение действует, только если совпадают все версии: `report_sha256`, `resume_sha256`, `source_sha256`, `requirements_sha256` и `policy_version`. Иначе оно `stale` и не учитывается. Повторный прогон может поменять вывод модели при том же id пункта, а другой кандидат на ту же вакансию — это другое резюме, поэтому решение не переносится. Решение о пункте, которого нет в текущей очереди, тоже `stale` (`unknown_item`).
   - `invalid` дают:
     - пункт одной вакансии, записанный под другой, в любую сторону (`foreign_job`);
     - повтор `decision_id` с другим содержанием в любом месте хранилища (`duplicate_decision`);
     - запись не от `recruiter` или не через `service` (`not_a_service_decision`). Такую запись нельзя отнести к вакансии, поэтому она делает недействительной оценку любой вакансии. Это сознательное «закрыто при ошибке».

     Так в коде реализовано правило ТЗ «чужая вакансия, повторяющиеся id или неподтверждённая ревизия → invalid». Ревизия, не совпадающая с текущей, даёт `stale`.
   - Решения других вакансий просто не относятся к этой.
4. **`read_context` не меняет статус.** `unknown` остаётся `unknown`, `fail` остаётся `fail`. Спорная обязательность не возвращается в жёсткую группу без отдельного исправления списка (E4).
5. **`accept_condition`** закрывает пункт конфликта как осознанное решение HR. Конфликт остаётся в `accepted_exceptions` и в отчёте.
6. Два одинаковых решения — одно решение. Перестановка вакансий результат не меняет. Массового auto-approve и автоматического отказа нет.
7. **Два канала подтверждения списка.**
   - Решение `confirm_requirements` сервис должен выполнять через E4 `approve()` на тех же `requirements_sha256`. После этого E4-проверка в отчёте покажет `confirmed`.
   - Пока отчёт не пересчитан, `requirements_confirmed` в оценке может быть `true`, а `verification.final_allowed` в отчёте — ещё `false`. Источник истины для передачи — эта оценка.

### Действие в очереди → решение

| Пункт очереди | `action` в очереди (что делает человек) | Решение, которое закрывает |
|---|---|---|
| `processing_error`, `incomplete_run` | `complete_run` | нет, блокер |
| `invalid_evidence` | `fix_source` | нет, блокер |
| `ambiguous_location` | `read_context` | нет, блокер: исправляется новым прогоном, где цитата однозначна |
| `requirements_stale` | `check_list` | нет, блокер: нужно новое подтверждение E4 |
| `requirements_unconfirmed`, `uncovered_text` | `check_list` | `confirm_requirements` |
| `mandatory_unbound` | `check_list` | `read_context` (балл не меняется, маркер не возвращается в жёсткую группу) |
| `disputed_negative`, `mandatory_fail`, `disputed_evidence` | `read_context` | `read_context` |
| `mandatory_unknown` | `ask_candidate` | `read_context` (статус остаётся `unknown`, вопрос кандидату — вне системы) |
| `privacy_may_hide` | `compare_with_original` | `read_context` |
| `condition_conflict` | `decide_condition` | `accept_condition` |

UI берёт кнопку из `closing_decision(item.reason_code)`, а не из `item.action`.

### Fixture решений

`evaluation/expectations/egor/e8-decisions.json` (генератор `make_e8_decisions.py`), четыре сценария на fixtures очереди:

| Сценарий | Решения | Итог |
|---|---|---|
| `normal-ready` | job-001: подтвердить список, отметить передачу | `reviewed_for_handoff` |
| `normal-open-unknown` | job-002: подтвердить, отметить, неизвестное Java не прочитано | `draft`, `marked_with_open_items` |
| `normal-unknown-read` | job-002: подтвердить, прочитать Java, отметить | `reviewed_for_handoff`, Java остаётся `unknown` |
| `disputed-blocked` | job-a: всё подтвердить, прочитать, принять конфликт, отметить | `blocked`: неоднозначная цитата и неполный запуск; конфликт в `accepted_exceptions` |

Тест сверяет состояние каждого сценария со значением, записанным вручную независимо от генератора. Остальные поля — снимок, записанный тем же кодом: он ловит изменения, но правильность не доказывает.

## Что должен проверить backend (Codex)

- Отчёт и его `report_sha256` берутся из опубликованного запуска, не от клиента. Решения записывает сервис с версиями из `current_versions`; UI решение не создаёт.
- Решения хранятся отдельным слоем рядом с запуском. Старый `evaluation` не меняется. Новый отчёт старые решения не наследует, они остаются в истории как `stale`.
- `job.conditions` — результат E5 `check_conditions(...).model_dump()`, когда Codex его подключит. До этого пунктов `condition_conflict` нет.
- `privacy` кладётся в отчёт, как сейчас в `application.analyze`.
- Очередь пересчитывается при каждом чтении отчёта; хранить её отдельно не нужно, id стабильны.

## Проверки

```sh
python -m unittest discover -s prototype/tests   # 176 OK (skipped=4): 26 test_review_queue, 28 test_review_policy
python -m unittest discover -s tests             # 10 OK
python scripts/check_repository.py               # PASS
python -m prototype demo; python -m prototype demo --scenario disputed
python evaluation/expectations/egor/make_e8_fixtures.py    # пересобирает те же fixtures очереди
python evaluation/expectations/egor/make_e8_decisions.py   # и fixture решений
```

Мутационная проверка — разовым скриптом вне репозитория: 20 правил очереди и 19 правил решений по очереди отключались, каждое ловится.

Второе ревью (E8b) нашло пять проблем, все исправлены с тестами:
- повтор `decision_id` между вакансиями не ловился;
- пункт чужой вакансии давал `stale`, а не `invalid`;
- принятый конфликт мог пропасть из-за порядка id решений;
- действия очереди и решения не были сопоставлены, а поле `final_ranking_allowed` путалось с E4 (переименовано в `processing_complete`);
- в причинах `stale` показывалась только первая изменённая версия.

Версия отчёта теперь не зависит от слоя проверки.

Независимое ревью нашло пять проблем, все исправлены с тестами:
- id не учитывали резюме, и решение могло перейти на другого кандидата;
- спорный `full` считался отрицательным выводом;
- форма условий E5 не проверялась;
- ссылки на условия не сверялись с текстами (теперь тест сверяет каждую ссылку с обработанным текстом и `locate`);
- документ говорил про v2, которой на этой базе нет.

## Ограничения

- Очередь и `assess_handoff` не подключены к pipeline, сервису и UI. Хранение решений — Codex.
- Ввода опыта из устного интервью нет: это отдельный будущий источник, как и сказано в ТЗ.
- Сигналы E5 появятся только после того, как Codex подключит `Conditions`. В fixture они подложены вручную.
- Приоритеты — правило команды. Порядок внутри приоритета не означает важность для найма.
- Fixture E6 сюда не подключены: в них нет отчётов модели. Использовать их можно после прогона раннера V6.
- Неоднозначные контексты E3 приходят одной строкой через « | »; очередь их разделяет. Если « | » встретится в тексте резюме, контекст разделится неверно.
