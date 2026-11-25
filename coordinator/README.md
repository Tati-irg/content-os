# Локальное состояние Content OS

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
