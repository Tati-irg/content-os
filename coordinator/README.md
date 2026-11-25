# Локальное состояние Content OS

## Автоматический оркестратор

`orchestrator.py` — рабочее stdlib-ядро для автоматической передачи между ролями. SQLite
сохраняет очередь, lease/attempt, события, версии, решения и SHA-256 артефактов. Каждый asset
имеет закрытый workspace. Никакая команда оркестратора не вызывает publisher и не публикует.

```sh
python3 coordinator/orchestrator.py --root /private/content-os init
python3 coordinator/orchestrator.py --root /private/content-os submit asset-1 brief.json --cycle CYCLE-1 --factcheck --idempotency-key request-1
python3 coordinator/orchestrator.py --root /private/content-os run-until-blocked
python3 coordinator/orchestrator.py --root /private/content-os approve asset-1 gate1 --actor 'Тата' --note 'ок'
python3 coordinator/orchestrator.py --root /private/content-os status asset-1
```

Все ответы CLI — JSON. DAG: research → 06 → GATE 1 → 07 → условный 08 → 07 final →
текстовый gate → 09 → audit → package → GATE 2 → release gate. `release` лишь фиксирует
явное разрешение человека; фактический запуск publisher остаётся отдельной операцией с его
собственным release guard.

Для подключения ролей положи `config.json` в корень состояния (секретов в нём быть не должно):

```json
{
  "lease_seconds": 300,
  "max_attempts": 3,
  "commands": {"plan06": ["python3", "/opt/roles/plan06.py"]},
  "notifier": {"type": "jsonl", "path": "/private/content-os/notifications.jsonl"}
}
```

Команда роли получает JSON на stdin и обязана вернуть JSON `{"content":"..."}` на stdout.
Вместо inline content разрешён путь `artifact`. Также поддержаны notifier `stdout` (CLI/event
stream) и `command`; внешняя команда получает JSON события на stdin. Метки уведомлений:
`[06 PLAN]`, `[07 TEXT]`, `[08 FACTCHECK]`, `[09 VISUAL]`, `[GATE]`.

Существующие чаты ChatGPT недоступны для программной записи: их нельзя использовать как event
bus. Отдельные видимые каналы требуют реальной интеграции — Telegram topics, Slack либо dashboard.
Для непрерывной работы нужен постоянно запущенный host/worker и явно настроенные bindings команд
и notifier. Без этого synthetic adapter полезен только для локального теста контура.

### Telegram topics: одноразовая настройка

1. Тата создаёт **private supergroup** в Telegram и включает Topics.
2. Через BotFather создаёт бота, добавляет его в эту группу администратором с правом читать и
   отправлять сообщения. Бот не умеет создать группу или добавить в неё самого себя.
3. Создаёт topics для research, 06 plan, 07 text, 08 fact-check, 09 visual и publication/gates,
   затем вручную отправляет по одному сообщению в каждом topic.
4. На постоянном закрытом host задаёт `TELEGRAM_BOT_TOKEN` (только env),
   `TELEGRAM_CONTROL_CHAT_ID` и `TELEGRAM_ALLOWED_USER_IDS=12345,67890`.
5. Запускает `python3 coordinator/orchestrator.py --root /private/content-os telegram-discover`.
   Команда вызывает `getMe/getUpdates`, печатает JSON с chat/topic IDs и никогда не печатает token.
6. Переносит IDs в конфиг:

```json
{"telegram":{"topics":{"research":11,"plan06":12,"text07":13,"factcheck08":14,
"visual09":15,"publication/gates":16},"allowed_user_ids":[12345]}}
```

После проверки запускается постоянный worker:

```sh
python3 coordinator/orchestrator.py --root /private/content-os serve --interval 2
```

Для cron допустима команда `telegram-poll-once`. Ingress принимает только точные команды
`/approve ASSET GATE [note]`, `/reject ASSET GATE [note]`, `/status ASSET`, только из настроенной
группы и от разрешённых user IDs. Все остальные сообщения лишь аудируются и не меняют состояние.
`update_id` и исходящие deliveries сохраняются в SQLite, поэтому повторы безопасны. Разрешение
`release` только фиксирует gate; бот не запускает publisher и не публикует в соцсети.

Храни каталог материала вне Git. Скрипт хранит версии, SHA-256 и историю изменений в `manifest.json`. Один координатор записывает результаты последовательно.

```sh
python3 coordinator/state.py /private/material init CYCLE_ID ASSET_ID GATE1_ID /private/input.md
python3 coordinator/state.py /private/material record-gate1 /private/gate1-source.md --approved-by 'Имя' --note 'Основание подтверждения'
python3 coordinator/state.py /private/material revise /private/draft.md --note 'Первая версия'
python3 coordinator/state.py /private/material verify
```

Перед записью GATE 1 сверяй фактическое одобрение. Результаты записывай командой `record VERSION STAGE FILE --note …`: `factcheck`, `visual`, `audit`, `package`, `gate2`. Если внешний фактчек не требуется, запиши основание. Пакет должен перечислять все утверждённые файлы, включая текст, проверки и входы публикатора. Формат каждой строки: `- [relative/path](relative/path) · \`sha256\``. Записывай GATE 2 после фактического одобрения пакета. `revise --visual-only` создаёт следующую версию для прежнего текста и снимает актуальность со старого пакета и его проверок.

Для восстановления размести распакованный материал в закрытом каталоге, вызови `verify`, затем [проверку готовности публикатора](../publisher/README.md). Для выпуска требуется отдельное разрешение.

Проверки из корня нового checkout: `python3 tests/test_coordinator.py` и `python3 tests/test_release_offline.py`. Для второй нужны зависимости публикатора (requests и Pillow), Linux и libseccomp. Тест создаёт искусственный материал во временном каталоге и блокирует сетевые вызовы на уровне ОС.
