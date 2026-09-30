#!/usr/bin/env python3
"""Bangun sc_map.json dari references/Detail_SCs.xlsx (sheet 'Pemetaan Posisi') + sc_manual.json.
Jalankan ulang setiap kali user memperbarui Excel (mis. kolom TODJO/BCP/BME terisi):
    python scripts/build_scmap.py [path/ke/Detail_SCs.xlsx]"""
import openpyxl, json, re, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
def norm(s): return re.sub(r"\s+", " ", re.sub(r"[_.\-/]+", " ", (s or "").lower())).strip()
def variants(tok):
    out = {norm(tok)}
    m = re.match(r"^(.*\s)?(\S+)/(\S+)$", tok.strip())      # 'Inspector Scaffolder/Scf' -> dua varian
    if m: out |= {norm((m.group(1) or "") + m.group(2)), norm((m.group(1) or "") + m.group(3))}
    return out
def main(xlsx=None):
    xlsx = xlsx or os.path.join(HERE, "..", "references", "Detail_SCs.xlsx")
    man = json.load(open(os.path.join(HERE, "sc_manual.json"), encoding="utf-8"))
    rows = list(openpyxl.load_workbook(xlsx, data_only=True)["Pemetaan Posisi"].iter_rows(values_only=True))
    hi = next(i for i, r in enumerate(rows) if r[0] and str(r[0]).startswith("Deskripsi Posisi"))
    cols = ["DJK" if str(c).strip().startswith("DJK") else str(c).strip() for c in rows[hi][1:]]
    out = {c: {} for c in cols}
    for r in rows[hi + 1:]:
        if not r[0]: continue
        pos = {"Commoun Labor": "Common Labor"}.get(str(r[0]).strip(), str(r[0]).strip())
        for c, cell in zip(cols, r[1:]):
            if not cell or c == "DJK": continue          # DJK: aturan Land 1/Land 2 ada di dailymp.py
            if c in man["tokens"]: continue              # SC ini memakai token manual
            for t in str(cell).split(","):
                if t.strip():
                    for v in variants(t): out[c][v] = pos
    for c, d in man["tokens"].items():
        out[c] = {}
        for pos, toks in d.items():
            for t in toks: out[c][norm(t)] = pos
    for c, d in man.get("extra", {}).items(): out.setdefault(c, {}).update(d)
    res = {k: v for k, v in out.items() if v}
    res["_sections"] = man["_sections"]; res["_forced"] = man["_forced"]
    json.dump(res, open(os.path.join(HERE, "sc_map.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print({k: len(v) for k, v in res.items() if not k.startswith("_")})
if __name__ == "__main__": main(sys.argv[1] if len(sys.argv) > 1 else None)
