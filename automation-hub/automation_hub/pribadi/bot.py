"""K1: bot Telegram (Bot API resmi, long polling, stdlib saja).

Jalankan: python -m automation_hub.pribadi.bot
Butuh .env: TELEGRAM_TOKEN=... dan ALLOWED_CHAT_IDS=111,222 (kosong = bot menolak semua).
"""
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

from ..common import config
from ..common.runlog import RunLog
from .entries import Queue, handle_message

API = "https://api.telegram.org/bot{token}/{method}"


def load_env(path=None):
    path = Path(path) if path else config.HUB_ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def call(token, method, **params):
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(API.format(token=token, method=method), data, timeout=60) as r:
        return json.load(r)["result"]


def run():
    load_env()
    token = os.environ.get("TELEGRAM_TOKEN")
    allowed = {int(x) for x in os.environ.get("ALLOWED_CHAT_IDS", "").split(",") if x.strip()}
    if not token:
        raise SystemExit("TELEGRAM_TOKEN belum diisi di .env")
    cfg = config.load()
    base = config.data_dir() / "07_pribadi"
    base.mkdir(parents=True, exist_ok=True)
    queue = Queue(base / "queue.jsonl")
    offset_file = base / "offset.txt"
    offset = int(offset_file.read_text()) if offset_file.exists() else 0
    log = RunLog("pribadi_bot")
    print("Bot jalan. Ctrl+C untuk berhenti.")
    try:
        while True:
            try:
                updates = call(token, "getUpdates", offset=offset, timeout=30)
            except OSError as e:
                log.warn(f"getUpdates gagal: {e}")
                time.sleep(10)
                continue
            for u in updates:
                offset = u["update_id"] + 1
                m = u.get("message")
                if m and m.get("text"):
                    chat, sender = m["chat"]["id"], m["from"]["id"]
                    if chat not in allowed:
                        log.skip(f"chat tidak diizinkan: {chat}")
                    else:
                        reply = handle_message(m["text"], m["date"], sender, cfg["categories"], queue)
                        call(token, "sendMessage", chat_id=chat, text=reply)
                        log.done(f"{sender}: {m['text']}")
                offset_file.write_text(str(offset))
    except KeyboardInterrupt:
        pass
    print(log.summary())


if __name__ == "__main__":
    run()
