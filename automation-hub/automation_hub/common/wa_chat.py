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
_OMITTED = re.compile(
    r"<(?:Media tidak disertakan|Media omitted|(?:image|video|audio|document|sticker|GIF) omitted)>", re.I)
_MARKERS = re.compile(
    r"<(?:Media tidak disertakan|Media omitted|(?:image|video|audio|document|sticker|GIF) omitted|album message)>"
    r"|\S+\.\w{2,5}\s+\((?:file terlampir|file attached)\)|<(?:attached|terlampir):[^>]+>", re.I)


def _clean(s):
    return s.translate(_INVISIBLE)


def date_order(lines):
    """'dmy' atau 'mdy' dari seluruh file: angka pertama/kedua > 12 menentukan; tanpa petunjuk = 'dmy'."""
    first_big = second_big = False
    for line in lines:
        m = ANDROID.match(line) or IOS.match(line)
        if m:
            first_big |= int(m["d"]) > 12
            second_big |= int(m["m"]) > 12
    return "mdy" if second_big and not first_big else "dmy"


def _ts(m, tz, order="dmy"):
    y = int(m["y"])
    y += 2000 if y < 100 else 0
    h = int(m["H"])
    ap = (m["ap"] or "").replace(".", "").lower()
    if ap == "pm" and h < 12:
        h += 12
    elif ap == "am" and h == 12:
        h = 0
    a, b = int(m["d"]), int(m["m"])
    day, month = (b, a) if order == "mdy" else (a, b)
    return datetime(y, month, day, h, int(m["M"]), int(m["S"] or 0),
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
        "caption": _MARKERS.sub("", text).strip(),
        "attachments": attachments,
        "media_omitted": bool(_OMITTED.search(text)),
        "system": system,
    }


def parse_chat(path, tz="Asia/Jakarta", order=None):
    """order: 'dmy' / 'mdy'; None = dideteksi dari isi file."""
    messages, cur = [], None
    with open(path, encoding="utf-8-sig") as f:
        lines = [_clean(l.rstrip("\r\n")) for l in f]
    order = order or date_order(lines)
    for line in lines:
        m = ANDROID.match(line) or IOS.match(line)
        if m:
            if cur:
                messages.append(_finish(cur))
            cur = {"ts": _ts(m, tz, order), "rest": m["rest"]}
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


def parse_to_jsonl(chat_path, out_path, tz="Asia/Jakarta", order=None):
    return write_jsonl(parse_chat(chat_path, tz, order), out_path)
