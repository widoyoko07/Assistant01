"""Work Description harus berbahasa Inggris. Butir berbahasa Indonesia diganti memakai kamus data/wd_en.json
({"kalimat asli": "English"}, tanpa tanda butir). Butir yang tampak Indonesia tapi belum ada di kamus dilaporkan,
tidak ditebak. Kamus ada di data/ (tidak masuk git) karena isinya teks pekerjaan proyek."""
import json
import re

from ..common import config as cfgmod

_INVISIBLE = re.compile("[‎‏⁠﻿]")
_PREFIX = re.compile(r"^(\s*(?:[-*•.]|\d+[.)])\s*)(.*)$", re.S)
_ID_WORDS = re.compile(
    r"\b(pemasangan|pekerjaan|pembuatan|pengecekan|pembersihan|penarikan|pemeriksaan|melanjutkan|lanjutkan|lanjut|masih|"
    r"kekurangan|dengan|untuk|yang|terminasi|lansir|langsir|modifikasi|akses|supervisi|perbaikan|bongkar|kabel|pasang|"
    r"tarik|rapih|bersih|dll|beberapa|pripare|stiring|dan|di|pindah|buka|tutup|ganti|siap|persiapan|galian|pengelasan|"
    r"pengecatan|pemotongan|sambung|inspeksi|hasil|kerja)\b", re.I)


def load_dict(root=None):
    path = cfgmod.data_dir(root=root) / "wd_en.json"
    if not path.exists():
        return {}
    return {_norm(k): v for k, v in json.loads(path.read_text(encoding="utf-8")).items()}


def _norm(s):
    return re.sub(r"\s+", " ", _INVISIBLE.sub("", s)).strip().casefold()


def looks_indonesian(core):
    return bool(_ID_WORDS.search(core))


def to_english(line, table):
    """(baris, status): status 'ok' (sudah Inggris atau diterjemahkan) atau 'perlu' (tampak Indonesia, belum ada di kamus)."""
    clean = _INVISIBLE.sub("", line)
    m = _PREFIX.match(clean)
    prefix, core = (m.group(1), m.group(2)) if m else ("", clean)
    hit = table.get(_norm(core))
    if hit is not None:
        return prefix + hit, "ok"
    return line, ("perlu" if looks_indonesian(core) else "ok")
