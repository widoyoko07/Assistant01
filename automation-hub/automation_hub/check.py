"""python -m automation_hub.check -- buat folder data/ yang hilang, laporkan config kosong."""
import sys

from .common import config

DATA_SUBDIRS = [
    "00_dropzone", "01_extracted", "02_mp", "03_mp_att", "04_photos",
    "05_dpr", "06_dagang", "07_pribadi", "archive", "logs",
]


def main(argv=None):
    cfg = config.load(argv[0] if argv else None)
    root = config.data_dir()
    for name in DATA_SUBDIRS:
        d = root / name
        if not d.exists():
            d.mkdir(parents=True)
            print(f"dibuat: {d}")
    missing = config.missing_keys(cfg)
    for k in missing:
        print(f"config kosong: {k}")
    print("OK" if not missing else f"{len(missing)} kunci config bermasalah")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
