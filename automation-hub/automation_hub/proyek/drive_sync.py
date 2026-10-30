"""M2: salin ZIP ekspor WA dari folder Google Drive for Desktop (drive Windows) ke data/inbox.

Drive for Desktop tampil sebagai huruf drive Windows (mis. H:) yang belum ter-mount di WSL, dan mount butuh sudo.
Jadi penyalinan lewat powershell.exe ke \\\\wsl.localhost. File yang ukurannya sama dengan salinan lokal dilewati.
"""
import subprocess
from pathlib import Path

from ..common import config as cfgmod
from ..common.runlog import RunLog


def _ps(cmd, timeout=600):
    r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or f"powershell keluar dengan kode {r.returncode}")
    return r.stdout


def list_remote(folder):
    """[(path Windows, ukuran)] semua .zip di folder Drive (rekursif)."""
    out = _ps(f"Get-ChildItem -LiteralPath '{folder}' -Recurse -File -Filter *.zip | ForEach-Object {{ $_.FullName + '|' + $_.Length }}")
    items = []
    for line in out.splitlines():
        path, _, size = line.strip().rpartition("|")
        if path and size.isdigit():
            items.append((path, int(size)))
    return items


def sync(cfg, root=None, log=None):
    """Salin ZIP baru/berubah dari cfg['drive']['local_root'] ke data/inbox. Kembalikan path lokal yang disalin."""
    log = log or RunLog("drive_sync", root=root)
    remote = cfg.get("drive", {}).get("local_root")
    if not remote:
        log.warn("drive.local_root belum diisi di config.yaml")
        return []
    inbox = cfgmod.data_dir(root=root) / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    unc = "\\\\wsl.localhost\\" + _distro() + str(inbox).replace("/", "\\")
    copied = []
    for path, size in list_remote(remote):
        name = path.rsplit("\\", 1)[-1]
        local = inbox / name
        if local.exists() and local.stat().st_size == size:
            continue
        _ps(f"Copy-Item -LiteralPath '{path}' -Destination '{unc}\\' -Force")
        log.done(name)
        copied.append(local)
    return copied


def _distro():
    import os
    return os.environ.get("WSL_DISTRO_NAME", "Ubuntu")
