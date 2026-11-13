# Защищённый runtime: факты и блокеры

13 ноября 2026, интеграционная ветка. Этот документ не объявляет protected live готовым.

## Что проверено

- Изолированное окружение `data/private/certum-sandbox/core/.venv`: Python 3.12.16, OpenAI SDK 3.29.0, Pydantic 2.14.1; добавлены python-docx 1.2.0 и lxml 6.1.3. `pip check` проходит. Текущие 59 тестов CLI выполняются в этом окружении и в самостоятельном Python 3.13.
- Настоящие core, PostgreSQL/tenant/vault и NER: `scripts/certum_smoke.py` проходит на вымышленных контактах, без OpenAI. Отсутствующие модели останавливают запуск до SDK.
- Core собран в локальный wheel: `certum_core-0.1.0-py3-none-any.whl`, 150 файлов, SHA256 `60202c5123f27a40fbb53d86c2bb2b4018b9b7fce17c14c93fb76e59235f5619`. В списке файлов нет .env/.venv/.git/data/private. Wheel лежит только в исключённом `data/private/runtime-artifacts/`, не опубликован.
- Источник core и его ревизия указаны в [настройке стенда](17-certum-local-setup.md). Новый [protected lock](../prototype/requirements.protected.lock.txt) фиксирует 139 зависимостей фактического окружения, включая исходные инструменты проверки core. Он не заменяет отдельный standalone lock.

## Блокеры

1. **Ложные NER-находки в профессиональных полях.** Полный путь настоящий core → настоящий SDK → локальный MockTransport → pipeline останавливается с `privacy_residual_findings`. В изначальной проверке после первого mock-ответа `SQL` в «Использовал SQL 1 год» распознан как компания. Отдельно воспроизведены лишние замены Python-разработчика/Excel в HR-примерах. Это не нехватка ключа API.
2. **Нельзя исправлять это широким исключением термина.** Независимый reviewer показал реальные NER-находки работодателя в «Создавала отчёты в Excel, где работала бухгалтером» и подрядчика в «Работала с SQL 1 год как с подрядчиком». Экспериментальные контекстные исключения удалены. В поставке остаётся исходный строгий анализатор core: неизвестный случай блокирует передачу. Требуется согласованное различение профессиональных понятий и сущностей с положительными и отрицательными примерами, а не отключение ORG/vault.
3. **Артефакт для команды и жюри.** В опубликованном репозитории core отсутствует; способ предоставления разрешённого пакета уточняется у владельца. Локальный wheel позволяет обсудить конкретную поставку, но не даёт права объявить внешний доступ готовым.
4. **Чистый protected Docker/Compose ещё не собран.** Проверенный standalone image — Python 3.13 с replay. Protected lock проверен в существующем Python 3.12 окружении; установка с нуля на Linux/втором компьютере и упаковка БД/моделей остаются приёмкой C3/V7.
5. **Protected live не выполнялся.** Первый ранее разрешённый платный synthetic Luna run был отдельным. В текущей работе нет новых расходов API. Новый live требует разрешённых данных/лимита и устранения предыдущих блокеров.

## Команды на подготовленном стенде

```sh
.venv/bin/python -m pip --python data/private/certum-sandbox/core/.venv/bin/python check
data/private/certum-sandbox/core/.venv/bin/python -m unittest discover -s prototype/tests -q
data/private/certum-sandbox/core/.venv/bin/python scripts/certum_smoke.py \
  --env-file data/private/certum-sandbox/core/.env \
  --tenant-file data/private/certum-sandbox/tenant-id \
  --models-dir data/private/certum-sandbox/models
# Диагностический путь с ответами replay вместо сети: сейчас ожидается exit 2.
data/private/certum-sandbox/core/.venv/bin/python scripts/certum_smoke.py \
  --env-file data/private/certum-sandbox/core/.env \
  --tenant-file data/private/certum-sandbox/tenant-id \
  --models-dir data/private/certum-sandbox/models --model-mock
```

После получения разрешённого wheel подготовлена следующая команда восстановления, **её чистая установка ещё не подтверждена**:

```sh
python3.12 -m venv .venv-protected
.venv-protected/bin/python -m pip install -r prototype/requirements.protected.lock.txt /path/to/certum_core-0.1.0-py3-none-any.whl
.venv-protected/bin/python -m pip check
```

Секреты стенда не копируются участникам. Каждый создаёт собственные БД, tenant и ключи по runbook. Исходники core в Git не добавлять до согласования способа поставки.
