"""End-to-end tests for the durable automatic coordinator (stdlib only)."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "coordinator" / "orchestrator.py"


class Flow(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, *args, ok=True):
        run = subprocess.run([sys.executable, str(CLI), "--root", str(self.root), *args],
                             text=True, capture_output=True)
        if ok:
            self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        return json.loads(run.stdout.strip().splitlines()[-1])

    def test_gated_flow_conditional_factcheck_and_idempotency(self):
        self.call("init")
        self.call("submit", "a1", '{"topic":"fixture"}', "--cycle", "c1",
                  "--factcheck", "--idempotency-key", "once")
        duplicate = self.call("submit", "ignored", "duplicate", "--idempotency-key", "once")
        self.assertEqual(duplicate["id"], "a1")
        blocked = self.call("run-until-blocked")
        self.assertEqual(blocked["last"]["gate"], "gate1")
        self.call("approve", "a1", "gate1", "--actor", "human")
        self.assertEqual(self.call("run-until-blocked")["last"]["gate"], "gate_text")
        stages = {x["stage"] for x in self.call("status", "a1")["artifacts"]}
        self.assertIn("factcheck08", stages)
        self.call("approve", "a1", "gate_text", "--actor", "human")
        self.assertEqual(self.call("run-until-blocked")["last"]["gate"], "gate2")
        self.call("approve", "a1", "gate2", "--actor", "human")
        self.assertEqual(self.call("run-until-blocked")["last"]["gate"], "release")
        self.assertEqual(self.call("status", "a1")["state"], "waiting_release")
        self.call("approve", "a1", "release", "--actor", "human")
        self.assertEqual(self.call("status", "a1")["state"], "release_authorized")

        self.call("submit", "a2", "no science")
        self.call("run-until-blocked")
        self.call("approve", "a2", "gate1", "--actor", "human")
        self.call("run-until-blocked")
        self.assertNotIn("factcheck08", {x["stage"] for x in self.call("status", "a2")["artifacts"]})

    def test_revision_marks_old_artifacts_stale(self):
        self.call("submit", "rev", "first")
        self.call("run-until-blocked")
        revised = self.call("revise", "rev", "second")
        self.assertEqual(revised["revision"], 2)
        self.assertTrue(all(a["status"] == "stale" for a in revised["artifacts"]))

    def test_retry_and_dead_letter(self):
        script = self.root / "fail.py"
        script.write_text("import sys; sys.exit(7)\n")
        config = self.root / "config.json"
        config.write_text(json.dumps({"max_attempts": 2, "commands": {"research": [sys.executable, str(script)]}}))
        self.call("submit", "bad", "fixture")
        self.assertEqual(self.call("run-once")["status"], "retry")
        db = sqlite3.connect(self.root / "orchestrator.sqlite3")
        db.execute("UPDATE jobs SET available_at='2000-01-01T00:00:00+00:00'")
        db.commit()
        self.assertEqual(self.call("run-once")["status"], "dead")
        self.assertEqual(self.call("status", "bad")["state"], "dead_letter")


if __name__ == "__main__":
    unittest.main()
