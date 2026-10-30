"""Loader config.yaml dengan validasi kunci wajib."""
from pathlib import Path

import yaml

HUB_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = HUB_ROOT / "config.yaml"

REQUIRED = {
    "groups": None,
    "categories": None,
    "drive": ["subcon_inbox", "dagang_inbox", "templates", "output"],
    "dpr": ["template", "filename", "no_start", "timezone"],
}


def load(path=None):
    path = Path(path) if path else DEFAULT_CONFIG
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def missing_keys(cfg):
    """Daftar kunci wajib yang hilang atau kosong, format 'bagian.kunci'."""
    out = []
    for section, keys in REQUIRED.items():
        val = cfg.get(section)
        if val in (None, "", {}, []):
            out.append(section)
            continue
        for k in keys or []:
            if not isinstance(val, dict) or val.get(k) in (None, ""):
                out.append(f"{section}.{k}")
    return out


def data_dir(cfg=None, root=None):
    return Path(root) if root else HUB_ROOT / "data"
