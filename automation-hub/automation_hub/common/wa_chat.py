"""M2: parser _chat.txt WhatsApp (Android dan iOS) -> messages.jsonl."""
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_INVISIBLE = dict.fromkeys(map(ord, "‎‏‪‬ ﻿"), None)

_DATE = r"(?P<d>\d{1,2})/(?P<m>\d{1,2})/(?P<y>\d{2,4})"
_TIME = r"(?P<H>\d{1,2})[.:](?P<M>\d{2})(?:[.:](?P<S>\d{2}))?\s*(?P<ap>[AaPp]\.?[Mm]\.?)?"
ANDROID = re.compile(rf"^{_DATE},?\s+{_TIME}\s+-\s+(?P<rest>.*)$")
IOS = re.compile(rf"^\[{_DATE},?\s+{_TIME}\]\s+(?P<rest>.*)$")

_ATTACH = [
    re.compile(r"(?P<f>\S+\.\w{2,5})\s+\((?:file terlampir|file attached)\)", re.I),
    re.compile(r"<(?:attached|terlampir):\s*(?P<f>[^>]+)>", re.I),
]
_OMITTED = re.compile(r"<(?:Media tidak disertakan|Media omitted)>", re.I)


def _clean(s):
    return s.translate(_INVISIBLE)


def _ts(m, tz):
    y = int(m["y"])
    y += 2000 if y < 100 else 0
    h = int(m["H"])
    ap = (m["ap"] or "").replace(".", "").lower()
    if ap == "pm" and h < 12:
        h += 12
    elif ap == "am" and h == 12:
        h = 0
    # format tanggal Indonesia: hari/bulan/tahun
    return datetime(y, int(m["m"]), int(m["d"]), h, int(m["M"]), int(m["S"] or 0),
                    tzinfo=ZoneInfo(tz)).isoformat()


def message_id(ts, sender, text):
    return hashlib.sha1(f"{ts}|{sender}|{text}".encode("utf-8")).hexdigest()[:16]


def _finish(raw):
    """raw: dict dengan ts, rest (mungkin multi-baris) -> pesan lengkap."""
    rest = raw["rest"]
    sender, sep, text = rest.partition(": ")
    system = not sep
    if system:
        sender, text = "", rest
    attachments = [m["f"].strip() for p in _ATTACH for m in p.finditer(text)]
    return {
        "id": message_id(raw["ts"], sender, text),
        "ts": raw["ts"],
        "sender": sender,
        "text": text,
        "attachments": attachments,
        "media_omitted": bool(_OMITTED.search(text)),
        "system": system,
    }


def parse_chat(path, tz="Asia/Jakarta"):
    messages, cur = [], None
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = _clean(line.rstrip("\r\n"))
            m = ANDROID.match(line) or IOS.match(line)
            if m:
                if cur:
                    messages.append(_finish(cur))
                cur = {"ts": _ts(m, tz), "rest": m["rest"]}
            elif cur is not None:
                cur["rest"] += "\n" + line
    if cur:
        messages.append(_finish(cur))
    return messages


def write_jsonl(messages, out_path):
    """Tulis dedupe-by-id; hasil sama untuk input sama."""
    seen, n = set(), 0
    with open(out_path, "w", encoding="utf-8") as f:
        for m in messages:
            if m["id"] in seen:
                continue
            seen.add(m["id"])
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
            n += 1
    return n


def merge_exports(*message_lists):
    """Gabung beberapa export yang tumpang tindih, urut waktu, tanpa duplikat."""
    by_id = {}
    for lst in message_lists:
        for m in lst:
            by_id.setdefault(m["id"], m)
    return sorted(by_id.values(), key=lambda m: m["ts"])


def parse_to_jsonl(chat_path, out_path, tz="Asia/Jakarta"):
    return write_jsonl(parse_chat(chat_path, tz), out_path)
