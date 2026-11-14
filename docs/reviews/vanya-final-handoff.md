# Передача задачи №6

## Поставки в интеграционной ветке

| Этап | Поставка и статус |
|---|---|
| V3. Экран рейтинга и источники | [PR №12](https://github.com/GrigoryPislegin/hackathon-phystech-nanimai/pull/12), `2b13040`, принят |
| V4. PDF/DOCX и ошибки файлов | [PR №13](https://github.com/GrigoryPislegin/hackathon-phystech-nanimai/pull/13), `46f0150`, принят |
| V5. Печатный пакет для менеджера | [PR №15](https://github.com/GrigoryPislegin/hackathon-phystech-nanimai/pull/15), `2243843`, принят. Краткий профиль, вывод по вакансии и конфликты условий для HR |
| V6. Проверка отчётов | Девять синтетических DOCX/PDF из [PR №23](https://github.com/GrigoryPislegin/hackathon-phystech-nanimai/pull/23), `1d1ed9e`, приняты. Ожидания Егора из [PR №16](https://github.com/GrigoryPislegin/hackathon-phystech-nanimai/pull/16) сохранены. Для оценки используется общий `evaluation.runner` |
| V7. Приёмка релиза | Оба replay с проверкой экспорта, Linux Docker CI для PR, состав контекста/образа, защита без корректных весов, готовность после повторного старта |

## Как воспроизвести

Локальный запуск и проверенная поставка описаны в [общей инструкции](../28-local-app-runbook.md).
На чистом checkout с Python 3.13 и зависимостями из `prototype/requirements.lock.txt`:

```sh
python -m prototype.privacy_core.prepare
python -m unittest discover -s prototype/tests -q
node --test prototype/tests/test_web_*.cjs
python scripts/check_cli_replays.py
```

Для проверки своих сохранённых отчётов создайте `manifest.json` рядом с ними
по [формату E9](egor-e9-runner.md). Источники E6 и отчёта должны совпадать
по обработанному тексту и хешам.

```sh
python -m evaluation.runner --reports /path/to/saved-reports \
  --expectations evaluation/expectations/egor/e6-cases.json \
  --split dev --out /path/to/summary --check
```

`--split holdout` дополнительно сверяет контрольную сумму сплита. `--check`
пишет JSON и Markdown и возвращает 1 при провале или пропуске ожидаемой
проверки. По умолчанию раннер формирует статистику и при неполном наборе.
Ошибка входа или записи даёт 2. Синтетическая регрессия записывает отчёт с
неверной цитатой на диск и проверяет код 1 и `wrong_evidence`.

Docker Linux amd64 с запущенным Docker Engine. Эта последовательность входит в
`Docker acceptance`:

```sh
docker build --platform linux/amd64 -t recruiter-ci .
docker run --rm --network none --entrypoint python recruiter-ci scripts/check_cli_replays.py --without-ui
docker run --rm --network none --entrypoint python recruiter-ci scripts/privacy_smoke.py --models-dir /opt/privacy-models --model-mock
bash .github/scripts/check-docker-boundaries.sh recruiter-ci
python3 scripts/check_container_stop.py --image recruiter-ci
```

Если хранилище публичных весов недоступно, [инструкция для локального импорта](../28-local-app-runbook.md#сборка-из-исходников)
проверяет оба SHA-256 до сборки. Все runtime-команды выполняются без сети.
В пустом образе проверяются служебные модули, файлы UI и отсутствие
`.env`, исходных документов, отчётов и legacy-сервисов. Синтетический CLI
отказывается начинать анализ без весов и с неверным SHA-256. HTTP-проверка
дожидается готовности до и после остановки. Оба останова должны дать код 0.

## Подтверждённые результаты и границы

- Чистый клон релиза `bffa94a13bd901b82c8a3491eed7676d66f9fcac`,
  macOS 15.7.3 arm64, Python 3.13.17, Node 24.14.0. Установка из lock, 404
  теста прототипа с NER, 40 JS-тестов и оба replay прошли. Docker на этом
  Mac недоступен. [Linux Docker CI релиза](https://github.com/GrigoryPislegin/hackathon-phystech-nanimai/actions/runs/43524689571)
  прошёл на том же SHA. [Второй физический Mac](egor-e10-second-computer.md)
  проверен на более раннем `48268b2`.
- Раннер E9 прочитал прежние синтетические отчёты V6. Прошли 45/45 строк dev,
  21/21 holdout и 4/4 условия. Подмена цитаты по React в dev дала 44/45 строк,
  `wrong_evidence` и код 1. Пустой набор live дал 0 оценённых случаев,
  качество модели не измерено.
- Ожидания E6 помечены `draft`. Смысл свободных формулировок, полнота извлечения
  и качество live остаются за отдельной экспертной проверкой. Для PDF нужна
  текстовая подложка. OCR в этом проходе отсутствует.
- Решение о принятии исправлений в интеграционную ветку остаётся за командой.
  V8–V11 относятся к следующему этапу.
