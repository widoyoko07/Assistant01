"""K1: bot Telegram (Bot API resmi, long polling, stdlib saja).

Jalankan: python -m automation_hub.pribadi.bot
Butuh .env: TELEGRAM_TOKEN=... dan ALLOWED_CHAT_IDS=111,-100222 (chat pribadi dan/atau grup;
kosong = bot menolak semua). Opsional ALLOWED_USER_IDS=111,333: di grup, hanya orang ini yang dilayani.
"""
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

from ..common import config
from ..common.runlog import RunLog
from .classify import load_lexicon
from . import ledger as ledger_mod
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


def try_sync(log, queue, base, cfg):
    """Kirim antrean ke Excel: file inbox (INBOX_PATH) atau Graph bila login ada. Gagal = antrean tetap."""
    from . import graph, inbox
    from .sync import sync_queue
    if not queue.all():
        return
    send = None
    if os.environ.get("INBOX_PATH"):
        send = lambda es: inbox.append_entries(os.environ["INBOX_PATH"], es)
    elif (base / "token.json").exists() and os.environ.get("MS_CLIENT_ID"):
        g = graph.Graph(os.environ["MS_CLIENT_ID"], base / "token.json")
        p = cfg["pribadi"]
        send = lambda es: g.add_rows(p["onedrive_path"], p["table"], [graph.row_values(e) for e in es])
    if not send:
        return
    try:
        n = sync_queue(send, queue, base / "sent.json")
        if n:
            log.done(f"Excel: {n} baris terkirim")
    except Exception as e:  # file terkunci, jaringan putus, token kedaluwarsa
        log.warn(f"sync Excel gagal, dicoba lagi: {e}")


def ledger_loader(queue, cfg):
    """Fungsi pembaca buku besar untuk /saldo dan /rekap, atau None bila lokasi file Excel tidak diketahui."""
    inbox = os.environ.get("INBOX_PATH")
    xlsx = os.environ.get("LEDGER_PATH") or (str(Path(inbox).parent / cfg["pribadi"]["ledger_file"]) if inbox else None)
    if not xlsx:
        return None
    return lambda: ledger_mod.load(xlsx, inbox, queue.all())


def single_instance(path):
    """Kunci agar hanya satu bot yang polling (dua bot = bentrok di Telegram). Kode keluar 3 bila sudah ada."""
    try:
        import fcntl
    except ImportError:  # Windows: tanpa kunci
        return None
    f = open(path, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise SystemExit(3)
    return f


def run():
    load_env()
    token = os.environ.get("TELEGRAM_TOKEN")
    allowed = {int(x) for x in os.environ.get("ALLOWED_CHAT_IDS", "").split(",") if x.strip()}
    users = {int(x) for x in os.environ.get("ALLOWED_USER_IDS", "").split(",") if x.strip()}
    if not token:
        raise SystemExit("TELEGRAM_TOKEN belum diisi di .env")
    cfg = config.load()
    base = config.data_dir() / "07_pribadi"
    base.mkdir(parents=True, exist_ok=True)
    lock = single_instance(base / "bot.lock")  # noqa: F841 (dipegang selama bot hidup)
    queue = Queue(base / "queue.jsonl")
    offset_file = base / "offset.txt"
    offset = int(offset_file.read_text()) if offset_file.exists() else 0
    ledger = ledger_loader(queue, cfg)
    lexicon = load_lexicon(base / "lexicon.json")  # dibuat oleh: python -m automation_hub.pribadi.learn <xlsx>
    me = call(token, "getMe")["username"]  # di grup perintah datang sebagai /bantuan@namabot
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
                    if chat not in allowed or (users and sender not in users):
                        log.skip(f"tidak diizinkan: chat={chat} user={sender}")
                    else:
                        reply = handle_message(m["text"].replace("@" + me, ""), m["date"], sender, cfg["categories"], queue, cfg.get("accounts"), lexicon, ledger)
                        call(token, "sendMessage", chat_id=chat, text=reply)
                        log.done(f"chat={chat} {sender}: {m['text']}")
                offset_file.write_text(str(offset))
            try_sync(log, queue, base, cfg)
    except KeyboardInterrupt:
        pass
    print(log.summary())


if __name__ == "__main__":
    run()
