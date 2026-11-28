#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Content OS Autopublisher — робот публикации из очереди queue/.
Запускается GitHub Actions по расписанию (15:00 МСК) или вручную.
Берёт манифесты, чьё publish_at <= сейчас, и постит во все сети, для которых есть ключи.
Ничего не постит без "approved": true и "gate2" в манифесте.
"""
import json, os, sys, time, urllib.request, urllib.parse, mimetypes, uuid
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "queue"
LOGS = ROOT / "logs"
LOGS.mkdir(exist_ok=True)

def env(n): return (os.environ.get(n) or "").strip()

def http_json(url, data=None, headers=None, method=None, raw=False):
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items(): req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
        return body if raw else json.loads(body.decode("utf-8"))

def http_post_form(url, fields, files=None, headers=None):
    boundary = "----co" + uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    for name, path in (files or {}).items():
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{Path(path).name}\"\r\nContent-Type: {ctype}\r\n\r\n".encode())
        parts.append(Path(path).read_bytes()); parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    h = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    h.update(headers or {})
    return http_json(url, data=b"".join(parts), headers=h, method="POST")

RAW_BASE = None  # выставляется в main из env GITHUB_REPOSITORY

def raw_url(rel):
    return f"https://raw.githubusercontent.com/{RAW_BASE}/main/{rel}"

# ---------- Сети ----------

def pub_tg(text, media):
    tok, chat = env("TG_BOT_TOKEN"), env("TG_CHAT_ID")
    if not tok or not chat: return "SKIP: нет ключей"
    api = f"https://api.telegram.org/bot{tok}"
    if not media:
        r = http_json(api + "/sendMessage", data=json.dumps({"chat_id": chat, "text": text}).encode(),
                      headers={"Content-Type": "application/json"}, method="POST")
    elif len(media) == 1:
        r = http_post_form(api + "/sendPhoto", {"chat_id": chat, "caption": text}, {"photo": media[0]})
    else:
        group = []
        for i, p in enumerate(media):
            group.append({"type": "photo", "media": f"attach://p{i}", **({"caption": text} if i == 0 else {})})
        files = {f"p{i}": p for i, p in enumerate(media)}
        r = http_post_form(api + "/sendMediaGroup", {"chat_id": chat, "media": json.dumps(group)}, files)
    if not r.get("ok"): raise RuntimeError(f"TG: {r}")
    return f"OK message_id={r['result'].get('message_id') if isinstance(r['result'], dict) else 'album'}"

def pub_max(text, media):
    tok, chat = env("MAX_BOT_TOKEN"), env("MAX_CHAT_ID")
    if not tok or not chat: return "SKIP: нет ключей"
    body = {"text": text[:4000]}
    if media:  # upload-хост MAX из Actions обычно доступен, но надёжнее публичная ссылка
        body["attachments"] = [{"type": "image", "payload": {"url": raw_url(media[0])}}]
    r = http_json(f"https://platform-api.max.ru/messages?chat_id={chat}",
                  data=json.dumps(body).encode(),
                  headers={"Authorization": tok, "Content-Type": "application/json"}, method="POST")
    return f"OK mid={r.get('message', {}).get('body', {}).get('mid', '?')}"

def pub_vk(text, media):
    tok, gid = env("VK_TOKEN"), env("VK_GROUP_ID")
    if not tok or not gid: return "SKIP: нет ключей"
    def call(method, **params):
        params.update({"access_token": tok, "v": "5.199"})
        r = http_json(f"https://api.vk.com/method/{method}", data=urllib.parse.urlencode(params).encode(), method="POST")
        if "error" in r: raise RuntimeError(f"VK {method}: {r['error'].get('error_msg')}")
        return r["response"]
    attachments = []
    for p in media:
        srv = call("photos.getWallUploadServer", group_id=gid)
        up = http_post_form(srv["upload_url"], {}, {"photo": p})
        saved = call("photos.saveWallPhoto", group_id=gid, photo=up["photo"], server=up["server"], hash=up["hash"])
        attachments.append(f"photo{saved[0]['owner_id']}_{saved[0]['id']}")
    r = call("wall.post", owner_id=f"-{gid}", from_group=1, message=text, attachments=",".join(attachments))
    return f"OK post_id={r.get('post_id')}"

def _warm_url(url, tries=12, pause=15):
    """Ждём, пока raw-кэш GitHub увидит свежий файл (иначе Meta получит 404)."""
    import urllib.error
    for i in range(tries):
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=30) as r:
                if r.status == 200: return True
        except Exception:
            pass
        time.sleep(pause)
    return False

def pub_ig(text, media):
    tok, ig = env("META_PAGE_TOKEN"), env("IG_USER_ID")
    if not tok or not ig: return "SKIP: нет ключей"
    def rel(p):
        s = str(p); i = s.find("queue/")
        return s[i:] if i >= 0 else s
    media = [rel(p) for p in media]
    for p in media:
        if not _warm_url(raw_url(p)): raise RuntimeError(f"картинка не появилась в raw-кэше: {p}")
    g = "https://graph.facebook.com/v21.0"
    def post(url, **params):
        import urllib.error
        params["access_token"] = tok
        try:
            r = http_json(g + url, data=urllib.parse.urlencode(params).encode(), method="POST")
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:400]
            raise RuntimeError(f"IG HTTP {e.code}: {body}")
        if "error" in r: raise RuntimeError(f"IG: {r['error'].get('message')}")
        return r
    def wait(cid):
        for _ in range(20):
            s = http_json(f"{g}/{cid}?fields=status_code&access_token={tok}")
            if s.get("status_code") == "FINISHED": return
            if s.get("status_code") == "ERROR": raise RuntimeError("IG container ERROR")
            time.sleep(5)
        raise RuntimeError("IG container timeout")
    if len(media) > 1:
        kids = []
        for p in media:
            c = post(f"/{ig}/media", image_url=raw_url(p), is_carousel_item="true"); kids.append(c["id"])
        cont = post(f"/{ig}/media", media_type="CAROUSEL", children=",".join(kids), caption=text)
    else:
        cont = post(f"/{ig}/media", image_url=raw_url(media[0]), caption=text)
    wait(cont["id"])
    time.sleep(15)  # инсте нужно «дойти» после FINISHED
    last = None
    for attempt in range(6):
        try:
            r = post(f"/{ig}/media_publish", creation_id=cont["id"])
            return f"OK media_id={r.get('id')}"
        except RuntimeError as e:
            last = e
            if "2207027" in str(e) or "not available" in str(e).lower():
                time.sleep(20); continue
            raise
    raise RuntimeError(f"не опубликовалось после ожидания: {last}")

def pub_fb(text, media):
    tok, page = env("META_PAGE_TOKEN"), env("FB_PAGE_ID")
    if not tok or not page: return "SKIP: нет ключей"
    g = "https://graph.facebook.com/v21.0"
    fields = {"message": text, "access_token": tok}
    fbids = []
    for p in media:
        r = http_post_form(f"{g}/{page}/photos", {**fields, "published": "false"}, {"source": p})
        if "error" in r: raise RuntimeError(f"FB photo: {r['error'].get('message')}")
        fbids.append(r["id"])
    for i, fid in enumerate(fbids):
        fields[f"attached_media[{i}]"] = json.dumps({"media_fbid": fid})
    r = http_json(f"{g}/{page}/feed", data=urllib.parse.urlencode(fields).encode(), method="POST")
    if "error" in r: raise RuntimeError(f"FB feed: {r['error'].get('message')}")
    return f"OK post_id={r.get('id')}"

NETWORKS = {"tg": pub_tg, "max": pub_max, "vk": pub_vk, "ig": pub_ig, "fb": pub_fb}

# ---------- Основной цикл ----------

def main():
    global RAW_BASE
    RAW_BASE = env("GITHUB_REPOSITORY") or "Tati-irg/content-os"
    now = datetime.now(timezone.utc)
    log = {"run_at": now.isoformat(), "results": []}
    manifests = sorted(QUEUE.glob("*/manifest.json"))
    if not manifests: print("Очередь пуста — делать нечего."); 
    for mp in manifests:
        m = json.loads(mp.read_text(encoding="utf-8"))
        slot = m.get("slot_id", mp.parent.name)
        entry = {"slot": slot, "networks": {}}
        try:
            pub_at = datetime.fromisoformat(m["publish_at"])
            if pub_at > now:
                entry["status"] = f"NOT DUE (ждёт {m['publish_at']})"; log["results"].append(entry); continue
            if not m.get("approved") or not m.get("gate2"):
                entry["status"] = "STOP: нет одобрения Таты (approved/gate2)"; log["results"].append(entry); continue
            for net, payload in m.get("networks", {}).items():
                fn = NETWORKS.get(net)
                if not fn:
                    entry["networks"][net] = "SKIP: неизвестная сеть"; continue
                media = [str(mp.parent / p) for p in payload.get("media", [])]
                try:
                    entry["networks"][net] = fn(payload.get("text", ""), media)
                except Exception as e:
                    entry["networks"][net] = f"ERROR: {e}"
            entry["status"] = "DONE"
            # переносим в обработанные
            done = LOGS / "done" / mp.parent.name
            done.mkdir(parents=True, exist_ok=True)
            for f in mp.parent.iterdir():
                f.rename(done / f.name)
            mp.parent.rmdir()
        except Exception as e:
            entry["status"] = f"ERROR: {e}"
        log["results"].append(entry)
    out = LOGS / f"{now.date().isoformat()}.json"
    prev = []
    if out.exists(): prev = json.loads(out.read_text(encoding="utf-8")).get("runs", [])
    prev.append(log)
    out.write_text(json.dumps({"runs": prev}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(log, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    sys.exit(main())
