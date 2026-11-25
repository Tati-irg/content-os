"""Mocked Telegram transport and approval ingress tests; no network or publishing."""
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "coordinator"))
import orchestrator


class Response:
    def __init__(self, value): self.value = value
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return json.dumps({"ok": True, "result": self.value}).encode()


class Telegram(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.root = Path(self.temp.name)
        self.config = self.root / "config.json"
        self.config.write_text(json.dumps({"telegram": {"control_chat_id": "-1001",
          "allowed_user_ids": [42], "topics": {"research": 11, "plan06": 12,
          "text07": 13, "factcheck08": 14, "visual09": 15, "publication/gates": 16}}}))
        self.calls, self.updates = [], []

    def tearDown(self): self.temp.cleanup()

    def urlopen(self, request, timeout=0):
        method = request.full_url.rsplit("/", 1)[-1]
        values = urllib.parse.parse_qs(request.data.decode())
        self.calls.append((method, values))
        if method == "getUpdates": return Response(self.updates)
        if method == "getMe": return Response({"id": 9, "username": "control_bot"})
        return Response({"message_id": len(self.calls)})

    def app(self): return orchestrator.Orchestrator(self.root, self.config)

    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "super-secret"}, clear=False)
    def test_topic_routing_and_delivery_ledger(self):
        with patch("urllib.request.urlopen", self.urlopen):
            app = self.app(); app.init()
            app.event("asset", 1, "stage.completed", {"stage": "plan06", "label": "[06 PLAN]"})
            send = [v for m, v in self.calls if m == "sendMessage" and v.get("message_thread_id") == ["12"]]
            self.assertEqual(len(send), 1)
            self.assertIn("[06 PLAN]", send[0]["text"][0])
            row = app.db.execute("SELECT status FROM telegram_deliveries ORDER BY event_id DESC LIMIT 1").fetchone()
            self.assertEqual(row["status"], "sent")
            self.assertNotIn("super-secret", json.dumps(self.calls))

    @patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "super-secret"}, clear=False)
    def test_auth_duplicate_approve_reject_and_status(self):
        with patch("urllib.request.urlopen", self.urlopen):
            app = self.app(); app.init(); app.submit("a", "c", {"brief": "x"}, False)
            app.run_until_blocked()
            self.updates = [
              {"update_id": 1, "message": {"chat": {"id": -1001}, "from": {"id": 99}, "text": "/approve a gate1 nope"}},
              {"update_id": 2, "message": {"chat": {"id": -1001}, "from": {"id": 42}, "text": "ok"}},
              {"update_id": 3, "message": {"chat": {"id": -1001}, "from": {"id": 42}, "text": "/approve a gate1 reviewed"}},
              {"update_id": 4, "message": {"chat": {"id": -1001}, "from": {"id": 42}, "text": "/status a"}},
            ]
            result = app.telegram_poll_once()
            self.assertEqual([x["status"] for x in result["updates"]], ["ignored", "ignored", "handled", "handled"])
            self.assertEqual(app.status("a")["state"], "gate1_approved")
            self.assertEqual(app.telegram_poll_once()["updates"], [])  # checkpoint + duplicate protection
            count = app.db.execute("SELECT count(*) FROM decisions").fetchone()[0]
            self.assertEqual(count, 1)
            self.assertFalse(any("publish.py" in str(call) for call in self.calls))

            app.run_until_blocked()
            self.updates = [{"update_id": 5, "message": {"chat": {"id": -1001}, "from": {"id": 42}, "text": "/reject a gate_text needs work"}}]
            app.telegram_poll_once()
            self.assertEqual(app.status("a")["state"], "gate_text_rejected")


if __name__ == "__main__": unittest.main()
