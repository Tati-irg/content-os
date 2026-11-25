# publisher

`publish.py` выкладывает один пост («слот») на выбранные площадки из слота.

```
python3 publisher/publish.py SLOT.json                                   # dry run (по умолчанию)
python3 publisher/publish.py SLOT.json --only ig,threads                      # только часть площадок
python3 publisher/publish.py --check-ready --manifest MANIFEST.json --version v2
```

## Маршрут VK

Om repost автоматически переносит публикации из Instagram в VK. Стандартный маршрут
пропускает прямую отправку в VK, даже если в старом слоте есть ключ `vk`, чтобы избежать дублей.
Прямой режим доступен при явном выборе `--only vk` для отдельных задач вне автопереноса.

## Локальная проверка и выпуск

- `python3 publisher/publish.py --check-ready --manifest /private/pilot/manifest.json --version v2` проверяет активный пакет без сети и слота. Та же команда доступна для `publish_carousel.py`.
- Dry run обоих публикаторов проверяет локальные входы. Он не загружает файлы и не создаёт контейнеры.
- Для реального запуска оба публикатора требуют `--publish --manifest … --version … --release …`. Манифест содержит `gate1_evidence` с путём и SHA-256 записи GATE 1. Запись связывает `decision: approved`, `approved_by`, `asset_id`, `cycle_id`, `gate1_id`, `input_sha256` и хеш исходного подтверждения в поле `source`. GATE 2 должен быть актуальным и связанным с SHA-256 пакета.
- JSON отдельного разрешения содержит `action: publish`, `asset_id`, `version`, `package_sha256`, `authorized_by`, `authorized_at`, `publisher` (имя скрипта), `platforms` (отсортированный список) и `inputs`. Для `publish.py` это объект с ключом `slot` и относительным путём в пакете. Для `publish_carousel.py` это `caption` и упорядоченный список `slides`. Все файлы должны быть перечислены в утверждённом пакете. Храни подтверждения в закрытом каталоге координатора. Это локальные доверенные записи, доступ на запись к ним должен быть ограничен.
- Стандартный порядок публикации — ig → fb → threads → tg → max. Ошибка на одной площадке не останавливает остальные.
- Если выбранная площадка не поддерживает утверждённый формат, проверка слота блокирует отправку до согласования отдельной адаптации. Карусель автоматически не сокращается до обложки.
- Для MAX явно укажи согласованный полный самостоятельный текст в `max.text_file` или `max.text`. При общем тексте для Telegram и MAX укажи один утверждённый файл в обоих блоках. Для карусели укажи утверждённое число изображений в `max.image_count`. Публикатор сверяет его с файлами, формирует одно сообщение с 2–12 статическими изображениями в порядке слайдов и проверяет число вложений и текст в ответе API. При расхождении ответ помечается ошибкой с ID сообщения, если он вернулся.
- Facebook и Instagram берут `META_PAGE_TOKEN` из окружения. В Codex Cloud прокси заменяет заполнитель HTTP-секрета для разрешённых доменов Meta. Threads передаёт `THREADS_ACCESS_TOKEN` в заголовке Bearer для прокси. VK использует авторизацию прокси. Telegram берёт `TELEGRAM_BOT_TOKEN` из окружения.
  Токены нигде не печатаются.

## Хостинг медиа

Оба публикатора используют [media_hosting.py](media_hosting.py). Git-репозиторий —
`https://github.com/Tati-irg/content-os.git`, ветка — `main`. База публичных ссылок —
`https://raw.githubusercontent.com/Tati-irg/content-os/main/media/`. Путь файла после базы —
`<asset_id>/<имя файла>`. Перед записью файлов оба публикатора сверяют адреса чтения и отправки
`origin` с настроенным Git-репозиторием.

Для загрузки нужны права на push, а для получения файлов площадками — публичный доступ по Raw.
Для локальной проверки адресов можно использовать `require_media_origin` и `media_url`.

## SLOT.json

```json
{
  "asset_id": "w41-1-ne-hochu",
  "kind": "carousel",
  "media": {
    "slides_dir": "runs/2026-W41/09/c1_ne_hochu",
    "image": "cover.png",
    "video": "reel.mp4",
    "cover": "reel_cover.png",
    "document": "dnevnik.pdf"
  },
  "ig":      {"caption_file": "ig.txt", "first_comment_file": "ig_comment.txt"},
  "tg":      {"text_file": "tg.txt", "attach_document": true},
  "threads": {"text_file": "threads.txt"}
}
```

- Пути — абсолютные или относительно папки, где лежит SLOT.json. Вместо `*_file` можно
  написать текст прямо: `caption`, `text`, `first_comment`.
- Нет ключа площадки — площадка пропускается. Один и тот же текстовый файл можно дать нескольким площадкам.
- Поддерживаемые форматы описаны ниже. Колонка VK относится к явному прямому режиму.

| kind | Instagram | Threads | VK | Telegram |
|---|---|---|---|---|
| `carousel` (`slides_dir`, `slide_*.png`) | карусель 2–10 | карусель 2–20 | фото (до 10 вложений вместе с PDF) | sendMediaGroup, затем текст |
| `image` (`image`) | фото | фото | фото | sendPhoto с подписью (≤1024), иначе фото + текст |
| `reels` (`video`, опц. `cover`) | Reels (resumable upload, share_to_feed) | видео | обложка + текст (видео в VK нужен user token) | sendVideo, затем текст |
| `story` (`image`, 1080×1920) | история | — | — | — |
| `text` | — | текст | текст | текст |

- `story` уходит только в Instagram (в VK истории идут через Om repost, в TG — автокросспостом), остальные ключи игнорируются.
- `ig.first_comment_file` — первый комментарий, публикуется только после настоящего `media_publish`.
- `media.document` (PDF) в прямом режиме VK прикрепляется, если указан (`"attach_document": false` — отключить);
  в Telegram — отдельным sendDocument, если `tg.attach_document: true`.
- Лимиты: подпись IG ≤ 2200 символов и ≤ 30 хештегов; Threads ≤ 500; Telegram ≤ 4096 (подпись ≤ 1024);
  VK ≤ 16000. Telegram — без parse_mode, превью ссылок отключены.

`publish_carousel.py` — старый скрипт только для карусели в Instagram, работает как раньше.
