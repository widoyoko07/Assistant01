"""M1: ekstrak ZIP export WhatsApp yang sudah diunduh ke data/00_dropzone/.

Pengunduhan dari Google Drive dilakukan Claude lewat konektor Drive; modul ini
mengurus nama grup -> kode SC, ekstraksi aman, manifest, dan dedupe lewat
processed.json (disimpan di folder Drive output oleh Claude).
"""
import hashlib
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from ..common import config as cfgmod
from ..common.runlog import RunLog

MAX_TOTAL_BYTES = 2 * 1024**3
KINDS = {".txt": "txt", ".jpg": "jpg", ".jpeg": "jpg", ".png": "jpg", ".pdf": "pdf",
         ".mp4": "video", ".mov": "video", ".3gp": "video"}
_NAME = re.compile(r"^(?:WhatsApp Chat(?: with| -)\s*)(?P<g>.+?)(?:\s*\(\d+\))?$", re.I)


def group_from_filename(zip_name):
    stem = Path(zip_name).stem
    m = _NAME.match(stem)
    return (m["g"] if m else stem).strip()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_extract(zip_path, dest, max_bytes=MAX_TOTAL_BYTES):
    """Tolak path absolut / '..' dan ZIP terlalu besar. Kembalikan daftar file."""
    dest = Path(dest)
    with zipfile.ZipFile(zip_path) as z:
        infos = [i for i in z.infolist() if not i.is_dir()]
        if sum(i.file_size for i in infos) > max_bytes:
            raise ValueError("ukuran ZIP terekstrak melebihi batas")
        for i in infos:
            p = PurePosixPath(i.filename.replace("\\", "/"))
            if p.is_absolute() or ".." in p.parts or re.match(r"^[A-Za-z]:", i.filename):
                raise ValueError(f"path berbahaya di ZIP: {i.filename}")
        dest.mkdir(parents=True, exist_ok=True)
        names = []
        for i in infos:
            target = dest / PurePosixPath(i.filename.replace("\\", "/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(i) as src, open(target, "wb") as out:
                out.write(src.read())
            names.append(str(target.relative_to(dest)))
    return names


def count_kinds(names):
    c = {"txt": 0, "jpg": 0, "pdf": 0, "video": 0, "lainnya": 0}
    for n in names:
        c[KINDS.get(Path(n).suffix.lower(), "lainnya")] += 1
    return c


def ingest(zip_path, cfg, processed, drive_id=None, root=None, log=None, now=None):
    """Proses satu ZIP. processed = {'sha256': [...], 'drive_ids': [...]} (diubah di tempat).
    Kembalikan manifest, atau None bila dilewati/gagal."""
    log = log or RunLog("ingest_zip", root=root)
    zip_path = Path(zip_path)
    digest = sha256_file(zip_path)
    if digest in processed.setdefault("sha256", []) or (drive_id and drive_id in processed.setdefault("drive_ids", [])):
        log.skip(f"{zip_path.name}: sudah pernah diproses")
        return None
    group = group_from_filename(zip_path.name)
    sc = cfg.get("groups", {}).get(group)
    if not sc:
        log.warn(f"{zip_path.name}: grup '{group}' tidak ada di config.groups, dihentikan")
        return None
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    dest = cfgmod.data_dir(root=root) / "01_extracted" / f"{sc}_{stamp}"
    try:
        names = safe_extract(zip_path, dest)
    except (ValueError, zipfile.BadZipFile) as e:
        log.warn(f"{zip_path.name}: {e}")
        return None
    manifest = {"sc": sc, "group": group, "drive_id": drive_id, "sha256": digest,
                "zip": zip_path.name, "counts": count_kinds(names)}
    (dest / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    processed["sha256"].append(digest)
    if drive_id:
        processed["drive_ids"].append(drive_id)
    log.done(f"{zip_path.name} -> {dest.name}")
    return manifest
