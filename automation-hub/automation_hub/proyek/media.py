"""M3b/M4: foto dari ekspor WA (dengan media) -> PDF Attendance per SC dan foto progres per laporan ME.

Lampiran dikaitkan lewat urutan pesan: foto yang dikirim berurutan oleh pengirim yang sama (selang kecil)
mengikuti pesan teks di depannya. Foto yang tertulis 'omitted' tidak ikut ekspor dan hanya dilaporkan.
"""
import csv
import shutil
from datetime import datetime
from pathlib import Path

from ..common import config as cfgmod
from ..common.runlog import RunLog
from . import me_report, tbm_split

IMAGE_EXT = {".jpg", ".jpeg", ".png"}
BURST_SECONDS = 120      # selang maksimum antar foto dalam satu kiriman
ATTENDANCE_WINDOW = 90   # foto form TBM dikirim bersama / tepat di sekitar pesan Posting
MAX_ATTENDANCE_PAGES = 3


def _t(msg):
    return datetime.fromisoformat(msg["ts"])


def _images(msg, media_dir):
    return [media_dir / a for a in msg.get("attachments", []) if (media_dir / a).suffix.lower() in IMAGE_EXT and (media_dir / a).is_file()]


def attendance_images(messages, posting_msg, media_dir):
    """Foto form TBM untuk satu pesan Posting: lampiran di pesan itu, atau dari pengirim yang sama
    dalam ATTENDANCE_WINDOW detik. Hanya file yang benar-benar ada di folder media."""
    t0, found = _t(posting_msg), []
    for m in messages:
        if m.get("system") or m["sender"] != posting_msg["sender"] or abs((_t(m) - t0).total_seconds()) > ATTENDANCE_WINDOW:
            continue
        found += [p for p in _images(m, media_dir) if p not in found]
    return found[:MAX_ATTENDANCE_PAGES]


def images_to_pdf(images, dest):
    from PIL import Image
    pages = []
    for p in images:
        with Image.open(p) as im:
            pages.append(im.convert("RGB").copy())
    pages[0].save(dest, "PDF", save_all=True, append_images=pages[1:], resolution=150)


def write_attendance(messages, sc, cfg, media_dir, root=None, log=None):
    """<SC> TBM <YYYYMMDD> Attendance.pdf ke data/02_mp untuk tiap tanggal yang punya foto form TBM."""
    log = log or RunLog("media", root=root)
    rule = cfg.get("tbm", {}).get(sc)
    if not rule:
        log.warn(f"{sc}: pengenal Posting belum ada di config.tbm, dilewati")
        return []
    media_dir = Path(media_dir)
    out_dir = cfgmod.data_dir(root=root) / "02_mp"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for d, msg in sorted(tbm_split.pick_postings(messages, rule, log).items()):
        imgs = attendance_images(messages, msg, media_dir)
        if not imgs:
            log.warn(f"{sc} {d}: foto form TBM tidak ikut ekspor, PDF Attendance tidak dibuat")
            continue
        path = out_dir / f"{sc} TBM {d.replace('-', '')} Attendance.pdf"
        images_to_pdf(imgs, path)
        log.done(path.name)
        written.append(path)
    return written


def report_photos(messages, cfg, media_dir):
    """[{'date','sc','ot','file'|None,'sender','ts'}] untuk foto di grup ME: foto beruntun dari pengirim yang sama
    mengikuti judul laporan SC di depannya. file None = foto tidak ikut ekspor."""
    aliases, media_dir = cfg.get("sc_aliases", {}), Path(media_dir)
    out, cur, last = [], None, None
    for m in messages:
        if m.get("system"):
            continue
        secs = [s for s in me_report.split_message(m, aliases) if s["sc"]]
        if secs:
            cur, last = (secs[0], m["sender"]), _t(m)
        elif cur and (m["sender"] != cur[1] or (_t(m) - last).total_seconds() > BURST_SECONDS):
            cur = None
        if cur is None:
            continue
        if m.get("attachments") or m.get("media_omitted"):
            last = _t(m)
            files = [media_dir / a for a in m["attachments"] if (media_dir / a).suffix.lower() in IMAGE_EXT] or [None]
            for f in files:
                out.append({"date": cur[0]["date"], "sc": cur[0]["sc"], "ot": cur[0]["ot"],
                            "file": f if f and f.is_file() else None, "sender": m["sender"], "ts": m["ts"]})
    return out


def write_photos(messages, cfg, media_dir, root=None, log=None):
    """Salin foto ke data/04_photos/<YYYYMMDD>/<SC>/<nn>_<nama asli> dan tulis manifest.csv."""
    log = log or RunLog("media", root=root)
    rows = report_photos(messages, cfg, media_dir)
    base = cfgmod.data_dir(root=root) / "04_photos"
    count, missing = {}, {}
    manifest = []
    for r in rows:
        key = (r["date"], r["sc"])
        if r["file"] is None:
            missing[key] = missing.get(key, 0) + 1
            continue
        count[key] = count.get(key, 0) + 1
        dest = base / r["date"].replace("-", "") / r["sc"] / f"{count[key]:02d}_{r['file'].name}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(r["file"], dest)
        manifest.append([r["date"], r["sc"], "Y" if r["ot"] else "", count[key], dest.name])
    for (d, sc), n in sorted(missing.items()):
        log.warn(f"{d} {sc}: {n} foto tidak ikut ekspor (omitted)")
    if manifest:
        with open(base / "manifest.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "sc", "overtime", "no", "file"])
            w.writerows(manifest)
    log.done(f"{len(manifest)} foto, {sum(missing.values())} hilang")
    return manifest
