#!/usr/bin/env python3
"""Durable, local Content OS orchestration.  This module never publishes."""
from __future__ import annotations

import argparse
import html
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import re

STAGES = ("research", "plan06", "gate1", "text07", "factcheck08", "text07_final",
          "gate_text", "visual09", "audit", "package", "gate2", "release")
GATES = {"gate1", "gate_text", "gate2", "release"}
LABELS = {"plan06": "[06 PLAN]", "text07": "[07 TEXT]", "text07_final": "[07 TEXT]",
          "factcheck08": "[08 FACTCHECK]", "visual09": "[09 VISUAL]"}


def now():
    return datetime.now(timezone.utc).isoformat()


def emit(value):
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


class Orchestrator:
    def __init__(self, root: Path, config: Path | None = None):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "orchestrator.sqlite3"
        self.config = {}
        if config:
            self.config = json.loads(config.read_text(encoding="utf-8"))
        elif (self.root / "config.json").exists():
            self.config = json.loads((self.root / "config.json").read_text(encoding="utf-8"))
        self.db = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")

    def init(self):
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS assets(
          id TEXT PRIMARY KEY, cycle_id TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
          state TEXT NOT NULL, factcheck_required INTEGER NOT NULL, workspace TEXT NOT NULL,
          input_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs(
          id INTEGER PRIMARY KEY AUTOINCREMENT, asset_id TEXT NOT NULL REFERENCES assets(id),
          revision INTEGER NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL,
          idempotency_key TEXT NOT NULL UNIQUE, attempts INTEGER NOT NULL DEFAULT 0,
          max_attempts INTEGER NOT NULL DEFAULT 3, available_at TEXT NOT NULL,
          lease_owner TEXT, lease_until TEXT, last_error TEXT, created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL, UNIQUE(asset_id, revision, stage));
        CREATE TABLE IF NOT EXISTS events(
          id INTEGER PRIMARY KEY AUTOINCREMENT, asset_id TEXT, revision INTEGER,
          type TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS artifacts(
          id INTEGER PRIMARY KEY AUTOINCREMENT, asset_id TEXT NOT NULL, revision INTEGER NOT NULL,
          stage TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL, status TEXT NOT NULL,
          created_at TEXT NOT NULL, UNIQUE(asset_id, revision, stage));
        CREATE TABLE IF NOT EXISTS decisions(
          id INTEGER PRIMARY KEY AUTOINCREMENT, asset_id TEXT NOT NULL, revision INTEGER NOT NULL,
          gate TEXT NOT NULL, decision TEXT NOT NULL, actor TEXT NOT NULL, note TEXT NOT NULL,
          created_at TEXT NOT NULL, UNIQUE(asset_id, revision, gate));
        CREATE TABLE IF NOT EXISTS telegram_deliveries(
          event_id INTEGER NOT NULL, part INTEGER NOT NULL, chat_id TEXT NOT NULL,
          thread_id INTEGER, status TEXT NOT NULL, message_id INTEGER, last_error TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          PRIMARY KEY(event_id,part));
        CREATE TABLE IF NOT EXISTS telegram_updates(
          update_id INTEGER PRIMARY KEY, status TEXT NOT NULL, reason TEXT,
          created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        self.event(None, None, "system.initialized", {"database": str(self.db_path)})

    def event(self, asset, revision, kind, payload):
        stamp = now()
        cursor = self.db.execute("INSERT INTO events(asset_id,revision,type,payload_json,created_at) VALUES(?,?,?,?,?)",
                        (asset, revision, kind, json.dumps(payload, ensure_ascii=False), stamp))
        notify = {"at": stamp, "asset_id": asset, "revision": revision, "event": kind, **payload}
        notifier = self.config.get("notifier", {"type": "stdout"})
        if notifier.get("type") == "jsonl":
            path = Path(notifier["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(notify, ensure_ascii=False) + "\n")
        elif notifier.get("type") == "command":
            subprocess.run(notifier["command"], input=json.dumps(notify), text=True,
                           shell=isinstance(notifier["command"], str), check=False)
        if self.telegram_enabled:
            self.telegram_deliver(cursor.lastrowid, notify)

    @property
    def telegram_enabled(self):
        return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and self.telegram_chat_id)

    @property
    def telegram_chat_id(self):
        return os.environ.get("TELEGRAM_CONTROL_CHAT_ID") or str(self.config.get("telegram", {}).get("control_chat_id", ""))

    def telegram_call(self, method, values=None):
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        url = f"https://api.telegram.org/bot{token}/{method}"
        data = urllib.parse.urlencode(values or {}).encode()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=30) as response:
                result = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            # Never include the token-bearing URL or response body in errors/events.
            raise ValueError(f"Telegram API {method} failed with HTTP {exc.code}") from None
        except urllib.error.URLError as exc:
            raise ValueError(f"Telegram API {method} unavailable: {exc.reason}") from None
        if not result.get("ok"):
            raise ValueError(f"Telegram API {method} rejected the request")
        return result.get("result")

    def telegram_topic(self, event):
        stage = event.get("stage") or event.get("gate")
        if stage in GATES:
            key = "decisions"
        elif stage in ("text07", "text07_final"):
            key = "text07"
        elif stage in ("audit", "package"):
            key = "publication/gates"
        else:
            key = stage or "publication/gates"
        topics = self.config.get("telegram", {}).get("topics", {})
        return topics.get(key), key

    def telegram_deliver(self, event_id, event):
        thread, topic = self.telegram_topic(event)
        label = event.get("label") or LABELS.get(event.get("stage"), "[SYSTEM]")
        lines = [f"<b>{html.escape(label)}</b>",
                 f"event: <code>{html.escape(str(event['event']))}</code>"]
        if event.get("asset_id"):
            lines.append(f"asset: <code>{html.escape(str(event['asset_id']))}</code>")
        for key in ("stage", "gate", "decision", "status", "error", "path", "sha256"):
            if event.get(key) is not None:
                value = str(event[key])
                # Keep notifications compact and avoid splitting inside escaped HTML entities.
                if len(value) > 350:
                    value = value[:347] + "..."
                lines.append(f"{html.escape(key)}: <code>{html.escape(value)}</code>")
        text_value = "\n".join(lines)
        parts = [text_value]
        for number, part in enumerate(parts):
            exists = self.db.execute("SELECT status FROM telegram_deliveries WHERE event_id=? AND part=?", (event_id, number)).fetchone()
            if exists and exists["status"] == "sent":
                continue
            stamp = now()
            self.db.execute("""INSERT OR IGNORE INTO telegram_deliveries
              (event_id,part,chat_id,thread_id,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)""",
              (event_id, number, self.telegram_chat_id, thread, "pending", stamp, stamp))
            values = {"chat_id": self.telegram_chat_id, "text": part, "parse_mode": "HTML",
                      "disable_web_page_preview": "true"}
            if thread is not None:
                values["message_thread_id"] = str(thread)
            try:
                reply = self.telegram_call("sendMessage", values)
                self.db.execute("UPDATE telegram_deliveries SET status='sent',message_id=?,updated_at=? WHERE event_id=? AND part=?",
                                (reply.get("message_id"), now(), event_id, number))
            except ValueError as exc:
                self.db.execute("UPDATE telegram_deliveries SET status='failed',last_error=?,updated_at=? WHERE event_id=? AND part=?",
                                (str(exc), now(), event_id, number))

    def allowed_telegram_users(self):
        raw = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
        values = [x.strip() for x in raw.split(",") if x.strip()]
        values.extend(str(x) for x in self.config.get("telegram", {}).get("allowed_user_ids", []))
        return set(values)

    def telegram_poll_once(self):
        if not self.telegram_chat_id:
            raise ValueError("TELEGRAM_CONTROL_CHAT_ID is required")
        checkpoint = self.db.execute("SELECT value FROM settings WHERE key='telegram_update_id'").fetchone()
        offset = int(checkpoint["value"]) + 1 if checkpoint else 0
        updates = self.telegram_call("getUpdates", {"offset": offset, "timeout": 0, "allowed_updates": '["message"]'})
        handled = []
        command = re.compile(r"^/(approve|reject)\s+([A-Za-z0-9_-]+)\s+(gate1|gate_text|gate2|release)(?:\s+(.{1,500}))?$|^/status\s+([A-Za-z0-9_-]+)$")
        for update in updates:
            update_id = int(update["update_id"])
            if self.db.execute("SELECT 1 FROM telegram_updates WHERE update_id=?", (update_id,)).fetchone():
                continue
            message = update.get("message") or {}
            chat_id = str((message.get("chat") or {}).get("id", ""))
            user_id = str((message.get("from") or {}).get("id", ""))
            text_value = message.get("text", "")
            match = command.fullmatch(text_value.strip())
            status, reason = "ignored", "unsupported_message"
            response = None
            if chat_id != str(self.telegram_chat_id):
                reason = "wrong_chat"
            elif user_id not in self.allowed_telegram_users():
                reason = "unauthorized_user"
            elif not match:
                reason = "invalid_command"
            else:
                try:
                    if match.group(5):
                        response = self.status(match.group(5)); status, reason = "handled", "status"
                    else:
                        action, asset, gate, note = match.group(1), match.group(2), match.group(3), match.group(4) or "Telegram approval"
                        response = self.decide(asset, gate, "approved" if action == "approve" else "rejected", f"telegram:{user_id}", note)
                        status, reason = "handled", action
                except ValueError as exc:
                    status, reason = "rejected", str(exc)
            self.db.execute("INSERT INTO telegram_updates(update_id,status,reason,created_at) VALUES(?,?,?,?)",
                            (update_id, status, reason, now()))
            self.db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('telegram_update_id',?)", (str(update_id),))
            self.event(response.get("id") if isinstance(response, dict) else None, response.get("revision") if isinstance(response, dict) else None,
                       "telegram.command", {"update_id": update_id, "status": status, "reason": reason, "user_id": user_id})
            if response is not None:
                compact = json.dumps({"ok": True, "state": response.get("state"), "asset_id": response.get("id")}, ensure_ascii=False)
                values = {"chat_id": self.telegram_chat_id, "text": compact}
                if message.get("message_thread_id") is not None:
                    values["message_thread_id"] = message["message_thread_id"]
                self.telegram_call("sendMessage", values)
            handled.append({"update_id": update_id, "status": status, "reason": reason})
        return {"offset": offset, "updates": handled}

    def telegram_discover(self):
        me = self.telegram_call("getMe")
        updates = self.telegram_call("getUpdates", {"timeout": 0})
        found = []
        for update in updates:
            message = update.get("message") or update.get("channel_post") or {}
            chat = message.get("chat") or {}
            if chat.get("id") is not None:
                found.append({"chat_id": chat["id"], "chat_title": chat.get("title"),
                              "message_thread_id": message.get("message_thread_id"), "update_id": update.get("update_id")})
        return {"bot": {"id": me.get("id"), "username": me.get("username")}, "topics": found}

    def serve(self, interval=2):
        while True:
            self.telegram_poll_once()
            self.run_until_blocked()
            time.sleep(interval)

    def enqueue(self, asset, revision, stage, delay=0):
        key = f"{asset}:{revision}:{stage}"
        stamp = now()
        available = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
        self.db.execute("""INSERT OR IGNORE INTO jobs
          (asset_id,revision,stage,status,idempotency_key,max_attempts,available_at,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?)""", (asset, revision, stage, "queued", key,
          int(self.config.get("max_attempts", 3)), available, stamp, stamp))

    def submit(self, asset, cycle, payload, factcheck, idem=None):
        self.init()
        if idem:
            row = self.db.execute("SELECT asset_id FROM events WHERE type='asset.submitted' AND json_extract(payload_json,'$.idempotency_key')=?", (idem,)).fetchone()
            if row:
                return self.status(row[0])
        stamp = now()
        workspace = self.root / "assets" / asset
        workspace.mkdir(parents=True, exist_ok=True)
        self.db.execute("""INSERT INTO assets(id,cycle_id,state,factcheck_required,workspace,input_json,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?)""", (asset, cycle, "queued", int(factcheck), str(workspace),
          json.dumps(payload, ensure_ascii=False), stamp, stamp))
        self.enqueue(asset, 1, "research")
        self.event(asset, 1, "asset.submitted", {"idempotency_key": idem, "factcheck_required": factcheck})
        return self.status(asset)

    def _claim(self, owner):
        stamp, until = now(), (datetime.now(timezone.utc) + timedelta(seconds=int(self.config.get("lease_seconds", 300)))).isoformat()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("""SELECT * FROM jobs WHERE
              (status='queued' AND available_at<=?) OR (status='running' AND lease_until<?)
              ORDER BY id LIMIT 1""", (stamp, stamp)).fetchone()
            if not row:
                self.db.execute("COMMIT")
                return None
            self.db.execute("""UPDATE jobs SET status='running', attempts=attempts+1,
              lease_owner=?,lease_until=?,updated_at=? WHERE id=?""", (owner, until, stamp, row["id"]))
            self.db.execute("COMMIT")
            return self.db.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone()
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def _adapter(self, asset, revision, stage):
        row = self.db.execute("SELECT * FROM assets WHERE id=?", (asset,)).fetchone()
        prior = [dict(x) for x in self.db.execute("SELECT stage,path,sha256 FROM artifacts WHERE asset_id=? AND revision=? AND status='current' ORDER BY id", (asset, revision))]
        request = {"asset_id": asset, "cycle_id": row["cycle_id"], "revision": revision,
                   "stage": stage, "input": json.loads(row["input_json"]), "artifacts": prior}
        command = self.config.get("commands", {}).get(stage)
        if command:
            result = subprocess.run(command if isinstance(command, list) else shlex.split(command),
                                    input=json.dumps(request, ensure_ascii=False), text=True,
                                    capture_output=True, timeout=int(self.config.get("command_timeout", 300)))
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or f"adapter exited {result.returncode}")
            response = json.loads(result.stdout)
            content = response.get("content")
            if content is None and response.get("artifact"):
                source = Path(response["artifact"]).resolve()
                if not source.is_file():
                    raise ValueError("adapter artifact does not exist")
                content = source.read_text(encoding="utf-8")
            if not isinstance(content, str):
                raise ValueError("adapter JSON must contain string content")
        else:
            content = json.dumps({"synthetic": True, **request}, ensure_ascii=False, indent=2)
        folder = Path(row["workspace"]) / f"v{revision}"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{stage}.json"
        path.write_text(content + ("" if content.endswith("\n") else "\n"), encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.db.execute("""INSERT OR REPLACE INTO artifacts(asset_id,revision,stage,path,sha256,status,created_at)
          VALUES(?,?,?,?,?,'current',?)""", (asset, revision, stage, str(path), digest, now()))
        return path, digest

    def run_once(self, owner=None):
        owner = owner or f"worker-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        job = self._claim(owner)
        if not job:
            return {"status": "idle"}
        asset, rev, stage = job["asset_id"], job["revision"], job["stage"]
        try:
            if stage in GATES:
                self.db.execute("UPDATE jobs SET status='waiting',lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=?", (now(), job["id"]))
                self.db.execute("UPDATE assets SET state=?,updated_at=? WHERE id=?", (f"waiting_{stage}", now(), asset))
                self.event(asset, rev, "gate.waiting", {"gate": stage, "label": "[GATE]"})
                return {"status": "blocked", "asset_id": asset, "gate": stage}
            path, digest = self._adapter(asset, rev, stage)
            self.db.execute("UPDATE jobs SET status='done',lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=?", (now(), job["id"]))
            row = self.db.execute("SELECT factcheck_required FROM assets WHERE id=?", (asset,)).fetchone()
            index = STAGES.index(stage) + 1
            next_stage = STAGES[index]
            if next_stage == "factcheck08" and not row["factcheck_required"]:
                self.event(asset, rev, "stage.skipped", {"stage": "factcheck08", "reason": "not required"})
                next_stage = "text07_final"
            self.enqueue(asset, rev, next_stage)
            self.db.execute("UPDATE assets SET state=?,updated_at=? WHERE id=?", (f"{stage}_done", now(), asset))
            self.event(asset, rev, "stage.completed", {"stage": stage, "label": LABELS.get(stage, "[SYSTEM]"), "path": str(path), "sha256": digest})
            return {"status": "done", "asset_id": asset, "stage": stage, "sha256": digest}
        except Exception as exc:
            terminal = job["attempts"] >= job["max_attempts"]
            delay = min(300, 2 ** max(0, job["attempts"] - 1))
            self.db.execute("""UPDATE jobs SET status=?,available_at=?,lease_owner=NULL,lease_until=NULL,
              last_error=?,updated_at=? WHERE id=?""", ("dead" if terminal else "queued",
              (datetime.now(timezone.utc)+timedelta(seconds=delay)).isoformat(), str(exc), now(), job["id"]))
            self.db.execute("UPDATE assets SET state=?,updated_at=? WHERE id=?", ("dead_letter" if terminal else "retrying", now(), asset))
            self.event(asset, rev, "job.dead_letter" if terminal else "job.retry", {"stage": stage, "error": str(exc), "attempt": job["attempts"]})
            return {"status": "dead" if terminal else "retry", "asset_id": asset, "stage": stage, "error": str(exc)}

    def run_until_blocked(self, limit=100):
        results = []
        for _ in range(limit):
            result = self.run_once()
            results.append(result)
            if result["status"] in {"idle", "blocked", "dead"}:
                break
        return {"results": results, "last": results[-1]}

    def decide(self, asset, gate, decision, actor, note):
        row = self.db.execute("SELECT * FROM assets WHERE id=?", (asset,)).fetchone()
        if not row:
            raise ValueError("unknown asset")
        rev = row["revision"]
        job = self.db.execute("SELECT * FROM jobs WHERE asset_id=? AND revision=? AND stage=?", (asset, rev, gate)).fetchone()
        if not job or job["status"] != "waiting":
            raise ValueError(f"{gate} is not awaiting a decision")
        self.db.execute("INSERT INTO decisions(asset_id,revision,gate,decision,actor,note,created_at) VALUES(?,?,?,?,?,?,?)",
                        (asset, rev, gate, decision, actor, note, now()))
        self.db.execute("UPDATE jobs SET status='done',updated_at=? WHERE id=?", (now(), job["id"]))
        if decision == "approved":
            if gate == "release":
                # An authorization record, not a publishing side effect.
                self.db.execute("UPDATE assets SET state='release_authorized',updated_at=? WHERE id=?", (now(), asset))
            else:
                self.enqueue(asset, rev, STAGES[STAGES.index(gate)+1])
                self.db.execute("UPDATE assets SET state=?,updated_at=? WHERE id=?", (f"{gate}_approved", now(), asset))
        else:
            self.db.execute("UPDATE assets SET state=?,updated_at=? WHERE id=?", (f"{gate}_rejected", now(), asset))
        self.event(asset, rev, "gate.decided", {"gate": gate, "decision": decision, "actor": actor, "note": note, "label": "[GATE]"})
        return self.status(asset)

    def revise(self, asset, payload):
        row = self.db.execute("SELECT * FROM assets WHERE id=?", (asset,)).fetchone()
        if not row:
            raise ValueError("unknown asset")
        old, rev = row["revision"], row["revision"] + 1
        self.db.execute("UPDATE artifacts SET status='stale' WHERE asset_id=? AND revision=?", (asset, old))
        self.db.execute("UPDATE jobs SET status='stale' WHERE asset_id=? AND revision=? AND status IN ('queued','waiting','running')", (asset, old))
        self.db.execute("UPDATE assets SET revision=?,state='queued',input_json=?,updated_at=? WHERE id=?",
                        (rev, json.dumps(payload, ensure_ascii=False), now(), asset))
        self.enqueue(asset, rev, "research")
        self.event(asset, rev, "asset.revised", {"supersedes": old})
        return self.status(asset)

    def status(self, asset=None):
        query = "SELECT * FROM assets" + (" WHERE id=?" if asset else " ORDER BY created_at")
        rows = self.db.execute(query, (asset,) if asset else ()).fetchall()
        values = []
        for row in rows:
            item = dict(row)
            item["factcheck_required"] = bool(item["factcheck_required"])
            item["jobs"] = [dict(x) for x in self.db.execute("SELECT stage,status,attempts,max_attempts,last_error FROM jobs WHERE asset_id=? AND revision=? ORDER BY id", (row["id"], row["revision"]))]
            item["artifacts"] = [dict(x) for x in self.db.execute("SELECT stage,path,sha256,status FROM artifacts WHERE asset_id=? ORDER BY id", (row["id"],))]
            values.append(item)
        if asset and not values:
            raise ValueError("unknown asset")
        return values[0] if asset else {"assets": values}

    def events(self, asset=None):
        rows = self.db.execute("SELECT * FROM events" + (" WHERE asset_id=?" if asset else "") + " ORDER BY id", (asset,) if asset else ()).fetchall()
        return {"events": [{**dict(r), "payload": json.loads(r["payload_json"])} for r in rows]}


def payload(value):
    if value == "-":
        return json.load(sys.stdin)
    path = Path(value)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"brief": value}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(".content-os"))
    parser.add_argument("--config", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    submit = commands.add_parser("submit")
    submit.add_argument("asset_id"); submit.add_argument("input")
    submit.add_argument("--cycle", default="default"); submit.add_argument("--factcheck", action="store_true")
    submit.add_argument("--idempotency-key")
    commands.add_parser("run-once")
    run = commands.add_parser("run-until-blocked"); run.add_argument("--limit", type=int, default=100)
    for name in ("approve", "reject"):
        p = commands.add_parser(name); p.add_argument("asset_id"); p.add_argument("gate", choices=sorted(GATES)); p.add_argument("--actor", required=True); p.add_argument("--note", default="")
    revise = commands.add_parser("revise"); revise.add_argument("asset_id"); revise.add_argument("input")
    status = commands.add_parser("status"); status.add_argument("asset_id", nargs="?")
    events = commands.add_parser("events"); events.add_argument("asset_id", nargs="?")
    commands.add_parser("telegram-poll-once")
    commands.add_parser("telegram-discover")
    serve = commands.add_parser("serve"); serve.add_argument("--interval", type=float, default=2)
    args = parser.parse_args()
    try:
        app = Orchestrator(args.root, args.config)
        if args.command == "init": app.init(); result = {"initialized": True, "database": str(app.db_path)}
        elif args.command == "submit": result = app.submit(args.asset_id, args.cycle, payload(args.input), args.factcheck, args.idempotency_key)
        elif args.command == "run-once": result = app.run_once()
        elif args.command == "run-until-blocked": result = app.run_until_blocked(args.limit)
        elif args.command in ("approve", "reject"): result = app.decide(args.asset_id, args.gate, "approved" if args.command == "approve" else "rejected", args.actor, args.note)
        elif args.command == "revise": result = app.revise(args.asset_id, payload(args.input))
        elif args.command == "status": result = app.status(args.asset_id)
        elif args.command == "telegram-poll-once": result = app.telegram_poll_once()
        elif args.command == "telegram-discover": result = app.telegram_discover()
        elif args.command == "serve": app.serve(args.interval); return
        else: result = app.events(args.asset_id)
        emit(result)
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        emit({"error": str(exc)}); raise SystemExit(1)


if __name__ == "__main__":
    main()
