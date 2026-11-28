#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Content OS Collector — приёмник материалов от Таты через Telegram-бота.
Запускается GitHub Actions каждые 15 минут (collector.yml).

Тата шлёт боту @irg_psy_post_bot с телефона:
  - видео (для Reels)  -> inbox/<дата-время>_video.mp4
  - голосовые/аудио (кейсы) -> inbox/<дата-время>_audio.<ext>
  - текст (темы, ответы на блиц) -> inbox/<дата-время>_text.txt
Бот отвечает ей подтверждением.

Защита: принимаем сообщения только от владельца. Первый написавший
запоминается в state/tg_owner.txt (проверено: это Тата), остальным — отказ.
"""
import json, os, sys, time, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "inbox"
STATE = ROOT / "state"
INBOX.mkdir(exist_ok=True)
STATE.mkdir(exist_ok=True)

TOK = (os.environ.get("TG_BOT_TOKEN") or "").strip()
API = f"https://api.telegram.org/bot{TOK}"
FILES = f"https://api.telegram.org/file/bot{TOK}"
MAX_FILE = 19 * 1024 * 1024  # Bot API отдаёт файлы до ~20 МБ

def http_json(url, data=None, timeout=60):
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def call(method, **params):
    r = http_json(f"{API}/{method}", data=urllib.parse.urlencode(params).encode())
    if not r.get("ok"): raise RuntimeError(f"TG {method}: {r}")
    return r["result"]

def reply(chat_id, text):
    try:
        call("sendMessage", chat_id=chat_id, text=text)
    except Exception as e:
        print(f"reply failed: {e}", file=sys.stderr)

def download(file_id):
    info = call("getFile", file_id=file_id)
    fp = info["file_path"]
    if info.get("file_size", 0) > MAX_FILE:
        raise OverflowError("файл больше 20 МБ — Telegram не отдаёт его боту")
    req = urllib.request.Request(f"{FILES}/{fp}")
    with urllib.request.urlopen(req, timeout=300) as r:
        return fp, r.read()

def main():
    if not TOK:
        print("Нет TG_BOT_TOKEN — выход."); return
    offset_f = STATE / "tg_offset.txt"
    owner_f = STATE / "tg_owner.txt"
    offset = int(offset_f.read_text().strip()) if offset_f.exists() else 0
    owner = owner_f.read_text().strip() if owner_f.exists() else ""

    got = 0
    while True:
        res = call("getUpdates", offset=offset, limit=100, timeout=0)
        if not res: break
        for up in res:
            offset = up["update_id"] + 1
            msg = up.get("message") or up.get("edited_message")
            if not msg: continue
            if msg.get("chat", {}).get("type") != "private": continue  # только личка
            user = msg.get("from", {})
            uid, chat_id = str(user.get("id")), msg["chat"]["id"]

            # --- замок владельца ---
            if not owner:
                owner = uid
                owner_f.write_text(f"{uid}  # {user.get('first_name','')} @{user.get('username','')}\n")
                print(f"OWNER LOCKED: {owner_f.read_text().strip()}")
            if uid != owner.split()[0]:
                reply(chat_id, "Этот бот служебный и работает только с владельцем 🙏")
                continue

            ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            try:
                if msg.get("text"):
                    name = f"{ts}_text.txt"
                    (INBOX / name).write_text(msg["text"], encoding="utf-8")
                    reply(chat_id, "Записал ✅ Текст улетел в банк материалов.")
                    got += 1
                else:
                    file_id, kind = None, None
                    if msg.get("video"):      file_id, kind = msg["video"]["file_id"], "video"
                    elif msg.get("video_note"): file_id, kind = msg["video_note"]["file_id"], "videonote"
                    elif msg.get("voice"):    file_id, kind = msg["voice"]["file_id"], "voice"
                    elif msg.get("audio"):    file_id, kind = msg["audio"]["file_id"], "audio"
                    elif msg.get("photo"):    file_id, kind = msg["photo"][-1]["file_id"], "photo"
                    elif msg.get("document"): file_id, kind = msg["document"]["file_id"], "file"
                    if not file_id:
                        reply(chat_id, "Такой тип сообщения я пока не умею принимать 🙈 "
                                       "Пришли видео, голосовое, аудио, фото или текст.")
                        continue
                    try:
                        fp, blob = download(file_id)
                    except OverflowError:
                        reply(chat_id, "Не влезло 🙈 Telegram отдаёт боту файлы до ~20 МБ. "
                                       "Пришли видео покороче (до ~60–90 сек) — оно сожмётся и пройдёт.")
                        continue
                    ext = Path(fp).suffix or ".bin"
                    name = f"{ts}_{kind}{ext}"
                    (INBOX / name).write_bytes(blob)
                    human = {"video": "Видео", "videonote": "Кружочек", "voice": "Голосовое",
                             "audio": "Аудио", "photo": "Фото", "file": "Файл"}.get(kind, "Файл")
                    reply(chat_id, f"{human} принял ✅ Лежит в банке материалов.")
                    got += 1
            except Exception as e:
                print(f"ERROR update {up['update_id']}: {e}", file=sys.stderr)
                reply(chat_id, "Что-то пошло не так при приёме 🙈 Ким разберётся, попробуй ещё раз позже.")
        if len(res) < 100: break

    offset_f.write_text(str(offset))
    print(f"Принято материалов: {got}. Offset: {offset}")

if __name__ == "__main__":
    sys.exit(main())
