# Очередь на публикацию

Один слот = одна папка `queue/<slot_id>/` с файлом `manifest.json` и картинками рядом.

Формат manifest.json:

```json
{
  "slot_id": "2026-11-30-mon-carousel",
  "publish_at": "2026-11-30T15:00:00+03:00",
  "approved": true,
  "gate2": "G2-0001",
  "networks": {
    "tg":  {"text": "текст для телеграма", "media": ["1.jpg", "2.jpg"]},
    "max": {"text": "текст для MAX", "media": ["1.jpg"]},
    "vk":  {"text": "текст для VK", "media": ["1.jpg", "2.jpg"]},
    "ig":  {"text": "подпись инсты", "media": ["1.jpg", "2.jpg"]},
    "fb":  {"text": "текст фейсбука", "media": ["1.jpg", "2.jpg"]}
  }
}
```

Правила (из протокола):
- Без `"approved": true` и `"gate2"` робот слот НЕ публикует (STOP).
- `publish_at` в будущем — робот ждёт.
- Сети без ключей в Secrets помечаются SKIP, остальные публикуются.
- После публикации папка переезжает в logs/done/, журнал — в logs/<дата>.json.
MEEOF
find /mnt/agents/work/content_os/gh_stage -type f | sort