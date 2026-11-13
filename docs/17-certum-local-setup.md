# Отдельный Certum для хакатона

Проверено 13 ноября 2026 на Mac владельца. Это локальный стенд защиты, не production и не готовый Docker-образ всего приложения. Исходники core не публикуются с этим проектом: права и способ передачи команде остаются отдельным вопросом. Личная база Certum не использовалась.

По уточнению владельца 13 ноября используем только технологию `certum_core` внутри нашего решения. Приложение/интерфейс Certum и подключение к чужому сервису не требуются. Указанные ниже источник и ревизия нужны для воспроизводимой зависимости; БД и секреты стенда созданы отдельно для хакатона.

Источник core: certum-assistant, ревизия `156c229b97e72e0df2cf3a647fc8083dd8f6667f`; SHA256 uv.lock `1879feb63251efb22b020046e9e53970f3acb59697261578ac83280d569629ea`. Эти идентификаторы позволяют отличить проверенное окружение от новой версии core.

## Что создано

- `data/private/certum-sandbox/core`: отдельная копия существующего certum-assistant/core без исходных .env/.venv; зависимости установлены по его uv.lock.
- `data/private/certum-sandbox/python`: CPython 3.12.16. Служебный uv установлен только в `/private/tmp/hackathon-python-tools`; этот временный каталог может исчезнуть.
- `data/private/certum-sandbox/models`: Slovnet/Navec, загруженные штатным downloader с проверкой SHA256.
- `data/private/certum-sandbox/core/.env`: новые случайные пароли и мастер-ключ; права 600, содержимое в логи не выводилось.
- `data/private/certum-sandbox/tenant-id`: id созданного тестового tenant, права 600.
- Compose project `hackathon-certum-isolated`, сервис `postgres`, отдельный том `hackathon-certum-isolated_pgdata`; порт только `127.0.0.1:55439`.

Весь каталог data/private исключён из Git и Docker-контекста CLI. Это не переносимый комплект для Вани: ему нужен легально предоставленный core и отдельная настройка.

## Повторная проверка на подготовленном Mac

Из корня проекта, Docker/OrbStack должен быть запущен:

```sh
docker compose --project-name hackathon-certum-isolated \
  --env-file data/private/certum-sandbox/core/.env \
  -f data/private/certum-sandbox/compose.yaml up -d --wait
data/private/certum-sandbox/core/.venv/bin/python scripts/certum_smoke.py \
  --env-file data/private/certum-sandbox/core/.env \
  --tenant-file data/private/certum-sandbox/tenant-id \
  --models-dir data/private/certum-sandbox/models
```

Ожидается JSON status=pass, real_certum=true, openai_calls=0. Скрипт принимает только PostgreSQL `postgresql+psycopg` на 127.0.0.1:55439 с базой certum, без query/fragment: чужой env-файл не должен направить smoke в удалённую базу. Проверяются прогрев детекторов и сейфа, замена вымышленных контактов (минимум три ссылки), сохранение профессионального предложения, повторный scan и конкретная ошибка privacy_untrusted_reference. Содержимое текста, ключи и DSN не печатаются. При ошибке выводится только класс исключения; подробную диагностику вести без раскрытия секретов.

Остановка без удаления данных:

```sh
docker compose --project-name hackathon-certum-isolated \
  --env-file data/private/certum-sandbox/core/.env \
  -f data/private/certum-sandbox/compose.yaml stop
```

Для удаления базы требуется отдельное осознанное действие; `down -v` в обычный сценарий не входит.

## Порядок развёртывания с нуля

1. Получить разрешённую локальную копию core, исключив чужие .env, .venv и личные данные. Создать отдельное закрытое окружение, не изменять исходный Certum.
2. Установить Python 3.12. В копии core выполнить `uv sync --locked --python 3.12`; не накладывать prototype/requirements.lock.txt.
3. Выполнить штатный `python scripts/make_env.py` внутри копии core. Он создаёт новые секреты только в файл 600. Для этого smoke используется отдельный локальный порт 55439 вместо штатного 55432; убедиться, что он свободен. Обе DSN и порт Compose должны совпадать. Если нужен другой порт, сначала явно изменить и проверить ограничение smoke, не подключаться к существующей базе по умолчанию.
4. Поднять только postgres отдельным Compose project и томом, проброс порта только на 127.0.0.1. Остальные сервисы dev-compose (relay, S3, core API, Docker proxy) для данного smoke не нужны.
5. В окружении core и из его каталога выполнить `certum migrate`, затем `certum tenant create --name hackathon-isolated-synthetic`. UUID из stdout сохранить отдельно; конфигурацию/ошибки с DSN не печатать в чат.
6. Штатная загрузка моделей: `python -m certum_core.detectors.models /абсолютный/путь/models`. При проблеме TLS использовать доверенные сертификаты certifi; проверку TLS не отключать.
7. Запустить `scripts/certum_smoke.py` командой выше с путями к своему тестовому стенду.

## Что это не подтверждает

- Общий реальный запрос Certum → OpenAI не выполнялся; отдельно прошли privacy smoke и live Luna на встроенной синтетике.
- Core lock использует OpenAI 3.29.0, CLI lock — 2.54.0; в core нет python-docx. Для единого runtime нужно согласовать зависимости и повторить тесты. Нынешние окружения намеренно раздельные.
- Не проверены другие компьютеры, Linux x86_64, полнота обезличивания реальных CV, доступ жюри к исходникам core и финальная упаковка защищённого пути.
