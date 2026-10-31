"""Cek kelengkapan data yang sudah diunggah, per SC, untuk satu tanggal laporan. Jalankan SEBELUM Daily MP / DPR.

    python -m automation_hub.proyek.cek_data --date 2026-10-30

Per SC: ZIP terbaru di data/inbox (ada foto atau tidak, tanggal chat terakhir) dan, untuk tanggal itu,
Posting.txt, Attendance PDF, dan foto progres. Hanya membaca, tidak mengubah apa pun.
"""
import argparse
import tempfile
import zipfile
from datetime import date
from pathlib import Path

from ..common import config as cfgmod
from ..common import wa_chat
from . import ingest_zip

IMG = {".jpg", ".jpeg", ".png"}


def zip_info(path):
    """{'name','images','last'} dari satu ZIP ekspor WA; last = tanggal pesan terakhir di chat."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        chat = next((n for n in names if n.lower().endswith(".txt")), None)
        last = None
        if chat:
            with tempfile.TemporaryDirectory() as t:
                p = Path(t) / "chat.txt"
                p.write_bytes(z.read(chat))
                msgs = wa_chat.parse_chat(p)
                last = max((m["ts"][:10] for m in msgs), default=None)
    return {"name": Path(path).name, "images": sum(Path(n).suffix.lower() in IMG for n in names), "last": last}


def latest_zips(inbox, cfg):
    """{SC: info ZIP dengan tanggal chat terakhir paling baru}."""
    best = {}
    for p in sorted(Path(inbox).glob("*.zip")):
        group = ingest_zip.group_from_filename(p.name)
        sc = "ME" if group == cfg.get("me_group") else cfg.get("groups", {}).get(group)
        if not sc:
            continue
        info = zip_info(p)
        if sc not in best or (info["last"] or "") > (best[sc]["last"] or ""):
            best[sc] = info
    return best


def check(cfg, day, root=None, inbox=None):
    """[(SC, dict)] untuk SC yang aktif. Nilai kosong/False = belum ada."""
    base = cfgmod.data_dir(root=root)
    inbox = Path(inbox) if inbox else base / "inbox"
    d8 = day.replace("-", "")
    skip = set(cfg.get("skip_sc", []))
    zips = latest_zips(inbox, cfg) if inbox.exists() else {}
    scs = [s for s in dict.fromkeys(list(cfg.get("groups", {}).values()) + list(cfg.get("tbm", {}))) if s not in skip]
    out = []
    if "ME" in zips:       # grup ME: sumber narasi dan foto progres, bukan SC
        z = zips["ME"]
        out.append(("ME", {"zip": z["name"], "images": z["images"], "last": z["last"], "posting": None, "attendance": None,
                           "photos": any((base / "04_photos" / d8).glob("*")) if (base / "04_photos" / d8).is_dir() else False}))
    for sc in scs:
        z = zips.get(sc)
        out.append((sc, {
            "zip": z["name"] if z else None,
            "images": z["images"] if z else 0,
            "last": z["last"] if z else None,
            "posting": (base / "02_mp" / f"{sc} TBM {d8} Posting.txt").exists(),
            "attendance": None if sc in cfg.get("attendance_in_posting", []) else ((base / "02_mp" / f"{sc} TBM {d8} Attendance.pdf").exists() or (base / "03_mp_att" / f"{sc}_{d8}_Attendance.txt").exists()),
            "photos": (base / "04_photos" / d8 / sc).is_dir(),
        }))
    return out


def report(rows, day):
    mark = lambda b: "-" if b is None else "✅" if b else "❌"
    lines = [f"Cek data {day}", "", "| SC | ZIP terbaru | Foto di ZIP | Chat s/d | Posting | Attendance | Foto progres |", "|---|---|---:|---|---|---|---|"]
    need = {"ZIP belum ada": [], "chat belum mencakup tanggal ini (ekspor ulang)": [], "ZIP tanpa foto": [],
            "Posting belum ada": [], "Attendance belum ada": []}
    for sc, r in rows:
        lines.append(f"| {sc} | {'✅' if r['zip'] else '❌ tidak ada'} | {r['images']} | {r['last'] or '-'}"
                     f"{' ⚠' if r['last'] and r['last'] < day else ''} | {mark(r['posting'])} | {mark(r['attendance'])} | {mark(r['photos'])} |")
        if not r["zip"]:
            need["ZIP belum ada"].append(sc)
        elif r["last"] and r["last"] < day:
            need["chat belum mencakup tanggal ini (ekspor ulang)"].append(sc)
        elif not r["images"]:
            need["ZIP tanpa foto"].append(sc)
        if r["posting"] is False:
            need["Posting belum ada"].append(sc)
        if r["attendance"] is False:
            need["Attendance belum ada"].append(sc)
    todo = [f"- {k}: {', '.join(v)}" for k, v in need.items() if v]
    lines += ["", "Perlu dilengkapi:" if todo else "Semua lengkap."] + todo
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--inbox")
    ap.add_argument("--root")
    a = ap.parse_args(argv)
    print(report(check(cfgmod.load(), a.date, root=a.root, inbox=a.inbox), a.date))


if __name__ == "__main__":
    main()
