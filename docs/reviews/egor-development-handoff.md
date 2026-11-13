# Handoff Егора: проверка доказательств и подтверждение требований

13 ноября 2026, ветка `egor/evidence-and-requirements` от `codex/cli-recruiter-prototype` (`e801e04`). SHA интеграции на момент работы не был опубликован.

- Новые модули локальные: без сети, модели и записи файлов.
- `contracts.py`, `model.py`, `privacy.py`, `pipeline.py`, `scoring.py` и `__main__.py` не менялись. Формат ответа модели прежний, миграция fixtures не нужна.
- **В pipeline и CLI модули не подключены** (`INTEGRATED = False`). Точки подключения — в конце документа.

## E3 — `prototype/evidence.py`

Точная цитата доказывает только то, что фрагмент есть в тексте. Модуль привязывает каждое доказательство к позиции, предложению и заголовку списка в **обработанном** тексте и выдаёт структурную проверку. Смысл он не подтверждает.

### Состояния

| `RowCheck.state` | Когда | Чем не является |
|---|---|---|
| `structure_ok` | Цитаты найдены, однозначны, равны целому предложению, связаны с требованием и стоят не под заголовком списка | Подтверждённым соответствием: `meaning` всегда `model_claim_unverified` |
| `needs_review` | Структура спорная (коды ниже) | Пятым статусом: статус модели `full/partial/fail/unknown` сохраняется |
| `no_evidence` | `unknown` без доказательств — нехватка сведений | Ошибкой |
| `invalid` | Техническая или структурная ошибка | `unknown`: ошибка остаётся ошибкой |

`MandatoryCheck.state`: `structure_ok`, `needs_review`, `not_mandatory`, `invalid`.

### Коды причин

| Код | Тяжесть | Что значит |
|---|---|---|
| `quote_is_fragment` | review | Цитата короче своего предложения; в `context` — предложение целиком |
| `quote_spans_sentences` | review | Цитата захватывает несколько предложений |
| `evidence_not_linked` | review | У доказательства и требования нет общего содержательного термина |
| `heading_context` | review | Цитата — пункт списка; в `context` — «заголовок → пункт» |
| `ambiguous_location` | review | Цитата факта стоит в разных местах резюме, позиции нет |
| `mandatory_not_linked` | review | Обязательность сказана в другом предложении или блоке |
| `mandatory_spans_segments` | review | Цитата обязательности захватывает несколько предложений |
| `ambiguous_requirement_location` | review | Цитата требования повторяется в вакансии, обязательность относится не ко всем вхождениям |
| `unknown_fact_id`, `quote_not_found`, `range_mismatch`, `empty_quote`, `unknown_source`, `source_mismatch`, `missing_evidence`, `unknown_with_evidence`, `duplicate_fact_id`, `requirement_mismatch`, `unknown_requirement_id` | invalid | Технические и структурные ошибки |

### Функции

```python
Source.of(source_id, text) -> Source                       # text — обработанный текст, хранит sha256
check_pair(requirements, facts, evaluation, cv: Source, vacancy: Source) -> PairCheck
check_row(row, requirement, facts, cv: Source) -> RowCheck
check_mandatory(requirement, vacancy: Source) -> MandatoryCheck
locate(source, quote, start=None) -> Located               # одно место или причина, почему нет
verify_span(span, sources: dict[str, Source]) -> list[Reason]   # повторная проверка сохранённого Span
layout(text) -> Layout                                     # предложения и заголовки; кешируется на текст
```

Результаты — Pydantic-модели, `model_dump()` кладётся в `report.json` как есть. `Span` хранит `source_id`, `source_sha256`, `start`, `end`, `quote`, `sentence` и `heading`.

### Пример (синтетика C01)

CV `Не работал с Python, планирую изучить.`, факт `quote='Python'`, строка `full`:

```json
{"requirement_id": "r1", "status": "full", "state": "needs_review",
 "meaning": "model_claim_unverified",
 "reasons": [{"code": "quote_is_fragment", "severity": "review", "fact_id": "f1",
              "context": "Не работал с Python, планирую изучить"}]}
```

Рекрутер видит предложение целиком. Срабатывает структурное правило «цитата короче предложения», а не список отрицаний. В `context` концевая пунктуация отрезана.

### Правила

1. **Привязка.**
   - Цитата ищется в обработанном тексте.
   - Если передана позиция, текст в этой позиции должен совпасть с цитатой дословно.
   - Если цитата стоит в разных предложениях, а позиции нет, место не выбирается.
2. **Целое предложение.**
   - Доказательство `full/partial/fail` равно своему предложению без маркера списка и концевой пунктуации.
   - Предложение кончается на `.!?;` только перед пробелом или концом строки, поэтому «Node.js», «ASP.NET Core», «3.5 года» целы.
3. **Связь с требованием.**
   - Нет ни одного общего содержательного термина → `evidence_not_linked`.
   - Общий термин связь не доказывает: «Строил отчёты в Excel» и «Python для автоматизации отчётов» делят «отчёт».
4. **Заголовок списка.**
   - Пункт под строкой с «:» получает `heading_context`, заголовок попадает в `Span.heading`.
   - Смысл заголовка код не читает, поэтому на проверку уходят и нейтральные «Навыки:».
5. **Обязательность.** `mandatory_quote` связан с требованием в двух случаях:
   - он стоит в том же предложении;
   - он является заголовком («Обязательно:»), а требование стоит в непрерывном списке прямо под ним (`-`, `*`, `•`, `–`, `1.`, `2)`). Список кончается на пустой строке и на первой строке без маркера («Желательно: SQL», «Будет плюсом»).

**Решение для Григория — правило 4.** Оно осторожное: у резюме-списков больше строк уйдёт на ручную проверку. Альтернатива — показывать заголовок, не меняя состояние. Тогда «Не работал с:\n- Python» пройдёт как `structure_ok`.

### Что код не ловит

- Модель цитирует целое предложение «Не работал с Python, планирую изучить.» и ставит `full` — структура пройдёт. Поэтому смысл всегда помечен как неподтверждённый.
- Случайный общий термин даёт `structure_ok` и для `fail`. **`structure_ok` не основание для `violated`** (см. п. 4 подключения).
- В «Python обязателен, SQL желателен.» обязательность Python стоит в том же предложении, что и SQL. Такая разметка пройдёт.
- Сокращения с пробелом («т. е.», «2019 г. — н. в.») режут предложение. Строка тогда уходит на проверку.
- Перечень под заголовком без маркеров не считается блоком обязательности и уходит на проверку.

## E4 — `prototype/requirements_review.py`

Если из «Python обязателен. Go обязателен.» извлечён один Python, сейчас получится `complete=true` и L=100. Модуль разделяет два состояния: «все вакансии обработаны» и «список требований проверен рекрутером». По умолчанию список не подтверждён.

```python
draft(vacancy_id, text, requirements) -> RequirementsDraft
    # state='unconfirmed'; uncovered — предложения вакансии, не задетые ни одной цитатой
approve(vacancy_id, text, requirements, approved_at) -> RequirementsApproval
    # только по явному действию рекрутера в CLI
check(approval | dict | None, vacancy_id, text, requirements) -> ApprovalCheck
    # confirmed | unconfirmed | stale | invalid
summarize(processing_complete, checks, *, expected_ids) -> RunReviewSummary
    # вакансия без проверки — unconfirmed, проверка чужой вакансии — invalid;
    # final_allowed = processing_complete and requirements_confirmed
requirements_sha256(requirements) -> str   # канонический JSON id/text/quote/mandatory_quote, порядок не важен
source_sha256(text) -> str
```

Пример (синтетика C04):

```python
draft('job-001', 'Python обязателен. Go обязателен.', only_python).uncovered   # ['Go обязателен']
```

Коды `stale`: `source_changed`, `requirement_added`, `requirement_removed`, `requirement_changed`, `mandatory_changed`.

Коды `invalid`:
- `malformed` — JSON модели или `approved_by` не `recruiter`;
- `schema_version`;
- `foreign_vacancy`;
- `hash_mismatch` — подтверждение не совпадает со своим же списком;
- `duplicate_ids`.

Ограничения:
- Подтверждение привязывает решение рекрутера к тексту и списку в однопользовательском CLI. Это не аутентификация и не подпись.
- `uncovered` работает по предложениям. В «Обязательно знание Python и Go.» при одном Python предложение уже задето, поэтому пропуск Go подсказка не покажет.

## Что подключить Codex

1. **`pipeline.py`, после `validate_pair` (стр. 35):** `evidence.check_pair(requirements, facts, evaluation, Source.of('cv', safe_resume), Source.of(jid, text))`. Результат положить в вакансию как `evidence_checks`.
2. **`pipeline.py`, после извлечения требований:**
   - `requirements_review.draft(jid, text, requirements)` → `requirements_review`;
   - подтверждение читать из закрытого каталога CLI и проверять через `check(...)`;
   - сводку строить так: `summarize(ranking['complete'], checks, expected_ids=[все jid])`.
3. **`write_report`:**
   - у `needs_review` показывать причину и `context`;
   - у `structure_ok` писать «структура проверена, смысл — утверждение модели»;
   - в шапке: «Требования подтверждены рекрутером: N из M» и `uncovered` неподтверждённых вакансий.
4. **`scoring.rank`** (решение Григория, L/H не меняется):
   - не выдавать `review_none_fit`, пока каждая обязательная строка `fail` во всех вакансиях не просмотрена человеком;
   - не выдавать `review_top` как итог при `needs_review` по обязательным у первого места или при `final_allowed=False`.
5. **SYSTEM в `model.py`:** «quote факта — целое предложение резюме; обязательность — фраза в том же предложении или заголовок списка, к которому относится требование».

## Проверка

```sh
python -m unittest discover -s prototype/tests -v   # 57 OK: 22 прежних, 20 evidence, 15 requirements_review
python -m unittest discover -s tests                # 10 OK
python scripts/check_repository.py                  # PASS
python -m prototype demo                            # отчёт без ключей
```

- **Синтетические случаи.** Тесты читают все случаи из `egor-cases-2026-11-13.json`. Ожидаемые ответы проходят, ловушки C01, C02, C03 и C08 получают `needs_review`.
- **Мутации.** Каждое правило по очереди отключалось в исходнике, и каждый раз падал хотя бы один тест.
- **Ревью.** Одно независимое ревью Opus (только чтение) нашло пять дефектов. Все исправлены, на каждый есть регрессионный тест.
- **Рефакторинг.** Разметка текста теперь считается один раз на текст. Новую версию сверил со старой на 60 000 случайных пар: коды, состояния и позиции совпали везде. Исключение — 3351 пара с цитатой требования из одних пробелов: раньше она проходила, теперь получает `invalid`.
- **Скорость.** CV на 59 000 символов, 20 вакансий × 15 строк × 10 фактов: было 32,4 с, стало 0,13 с.
- **Не проверено.**
  - `demo --scenario disputed`: в базе `e801e04` этого сценария нет.
  - Повтор `egor_review_repro.py` (PR #2) на SHA интеграции: SHA не опубликован.
