"""Bangun lexicon kategori dari riwayat 04.record.
Jalankan: python -m automation_hub.pribadi.learn "path/ke/Doku Keluarga.xlsx"
Hasil: data/07_pribadi/lexicon.json (berisi deskripsi pribadi; ada di data/ jadi tidak masuk Git)."""
import sys

from ..common import config
from .classify import build_lexicon, save_lexicon
from .records import read_records

LEXICON = config.data_dir() / "07_pribadi" / "lexicon.json"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    recs = read_records(sys.argv[1])
    lex = build_lexicon(recs)
    save_lexicon(lex, LEXICON)
    print(f"{len(recs)} baris -> {len(lex['phrases'])} frasa, {len(lex['tokens'])} kata. Disimpan: {LEXICON}")
