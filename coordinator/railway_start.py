"""Safe Railway entrypoint for the persistent Content OS coordinator."""
import json
import os
from pathlib import Path
import subprocess
import sys


def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"missing required environment variable: {name}")
    return value


def main():
    if os.environ.get("CONTENT_OS_LIVE") != "YES":
        raise SystemExit("worker is locked; set CONTENT_OS_LIVE=YES only after the no-publish review")

    root = Path(os.environ.get("CONTENT_OS_STATE_DIR", "/data"))
    root.mkdir(parents=True, exist_ok=True)
    commands = json.loads(required("CONTENT_OS_COMMANDS_JSON"))
    needed = {"research", "plan06", "text07", "text07_final", "visual09", "audit", "package"}
    missing = sorted(needed - commands.keys())
    if missing:
        raise SystemExit("real role adapters are missing: " + ", ".join(missing))

    config = {
        "commands": commands,
        "telegram": {
            "control_chat_id": required("TELEGRAM_CONTROL_CHAT_ID"),
            "allowed_user_ids": [int(x) for x in required("TELEGRAM_ALLOWED_USER_IDS").split(",")],
            "topics": {
                "research": int(required("TELEGRAM_TOPIC_RESEARCH")),
                "plan06": int(required("TELEGRAM_TOPIC_PLAN")),
                "text07": int(required("TELEGRAM_TOPIC_TEXT")),
                "factcheck08": int(required("TELEGRAM_TOPIC_FACTCHECK")),
                "visual09": int(required("TELEGRAM_TOPIC_VISUAL")),
                "publication/gates": int(required("TELEGRAM_TOPIC_PUBLICATION")),
                "decisions": int(required("TELEGRAM_TOPIC_DECISIONS")),
            },
        },
    }
    config_path = root / "config.json"
    temporary = root / "config.json.tmp"
    temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(config_path)
    subprocess.run([
        sys.executable, str(Path(__file__).with_name("orchestrator.py")),
        "--root", str(root), "--config", str(config_path), "serve", "--interval", "2"
    ], check=True)


if __name__ == "__main__":
    main()
