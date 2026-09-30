#!/usr/bin/env python3
"""Cross-check Attendance (teks ternormalisasi dari PDF) vs Posting. Dipanggil dari dailymp.py --xc.

Format file Attendance .txt (satu orang per baris; dibuat Claude dari hasil baca PDF):
    <Nama> [Role] <PT/CV>          contoh: 'Ifan Docon SILOG'  |  'Slamet Dwi Insp Scaffolder SILOG'
Header seksi = baris huruf kapital tanpa angka ('ERN', 'LPS'). Hanya baris yang PT/CV-nya memuat nama SC yang dihitung
(OWJJ dan PT lain dilewati). Nomor di awal baris boleh ada. Baris 'TOTAL MANPOWER: 118' opsional.
Nama file: <SC>_<YYYYMMDD>_Attendance.txt  (mis. SILOG_20260929_Attendance.txt)
"""
import re, os, sys, difflib

ROLE_WORDS = {"pm", "dpm", "cm", "dcm", "sm", "se", "pc", "ppc", "qc", "qa", "eng", "engineer", "docon", "matecon", "matkon",
              "admin", "driver", "hse", "coor", "coordinator", "spv", "supervisor", "foreman", "foremen", "fm", "helper",
              "teknisi", "welder", "rigger", "skill", "scaffolder", "scaffolding", "insp", "inspector", "operator", "tmc",
              "crane", "si", "pulling", "survey", "surveyor", "mandor", "fitter", "checker", "housekeeping"}

def nn(s): return re.sub(r"[^a-z]", "", (s or "").lower())
def toks(s): return {t for t in re.split(r"[^a-z]+", (s or "").lower()) if t}
def sim(a, b): return difflib.SequenceMatcher(None, nn(a), nn(b)).ratio()

def find_attendance(folder, sc, d):
    key = d.replace("-", "")
    for f in sorted(os.listdir(folder)):
        l = f.lower()
        if l.endswith(".txt") and "attendance" in l and l.startswith(sc.lower()) and key in f: return os.path.join(folder, f)
    return None

def parse_att(text, sc):
    people, section, stated = [], "Manpower", None
    sc_l = sc.lower()
    for raw in text.splitlines():
        line = raw.strip()
        if not line: continue
        m = re.match(r"(?i)^total\s*manpower\s*[:=]?\s*(\d+)?", line)
        if m:
            if m.group(1): stated = int(m.group(1))
            continue
        line = re.sub(r"^\d+[\s.)]+", "", line).strip()
        parts = line.rsplit(None, 1)
        if len(parts) == 2 and (sc_l in parts[1].lower() or parts[1].lower() == "owjj"):
            body, ptcv = parts
            if sc_l not in ptcv.lower(): continue          # OWJJ / PT lain bukan MP SC ini
            words, role = body.split(), []
            while len(words) > 1 and nn(words[-1]) in ROLE_WORDS: role.insert(0, words.pop())
            people.append({"name": " ".join(words), "role": " ".join(role) or None, "section": section})
        elif re.match(r"^[A-Z][A-Z0-9 ()/&.\-]*$", line) and not re.search(r"\d", line):
            section = line
    return people, stated

def crosscheck(att, post, thr=0.82):
    ua, up, exact, fuzzy, subset = set(), set(), [], [], []
    for i, a in enumerate(att):
        for j, p in enumerate(post):
            if j not in up and nn(a["name"]) == nn(p["name"]):
                exact.append((a, p)); ua.add(i); up.add(j); break
    for i, a in enumerate(att):
        if i in ua: continue
        best, bj = 0, None
        for j, p in enumerate(post):
            if j in up: continue
            s = sim(a["name"], p["name"])
            if s > best: best, bj = s, j
        if bj is not None and best >= thr: fuzzy.append((a, post[bj], best)); ua.add(i); up.add(bj)
    for i, a in enumerate(att):                              # nama singkat vs lengkap ('Thariq' vs 'M. Thariq Alfian')
        if i in ua: continue
        at = toks(a["name"])
        c = [j for j, p in enumerate(post) if j not in up and len(nn(p["name"])) >= 4 and toks(p["name"]) and
             (toks(p["name"]) <= at or at <= toks(p["name"]))]
        if len(c) == 1: subset.append((a, post[c[0]])); ua.add(i); up.add(c[0])
    return {"exact": exact, "fuzzy": fuzzy, "subset": subset,
            "only_att": [a for i, a in enumerate(att) if i not in ua], "only_post": [p for j, p in enumerate(post) if j not in up]}

def report(sc, d, att, att_stated, post, post_stated):
    r = crosscheck(att, post)
    f = lambda x: f"{x['name']} ({x['role'] or x['section']})"
    L = [f"### Cross-check {sc} {d}: Attendance vs Posting",
         f"PDF {len(att)} orang" + (f" (tertulis {att_stated})" if att_stated else "") + f" | Posting {len(post)} orang (setelah dedup)" +
         (f", tertulis {post_stated}" if post_stated else "") +
         f" | cocok persis {len(r['exact'])}, ejaan beda {len(r['fuzzy'])}, nama singkat/lengkap {len(r['subset'])}, "
         f"hanya di PDF {len(r['only_att'])}, hanya di Posting {len(r['only_post'])}"]
    if r["only_att"]: L.append(f"- Hanya di PDF ({len(r['only_att'])}; hadir tapi tidak tercatat di TBM, minta koreksi): " + "; ".join(map(f, r["only_att"])))
    if r["only_post"]: L.append(f"- Hanya di Posting ({len(r['only_post'])}; tidak tanda tangan / belum hadir): " + "; ".join(map(f, r["only_post"])))
    pairs = [(a, p) for a, p, _ in r["fuzzy"]] + r["subset"]
    if pairs: L.append("- Ejaan/nama beda, dianggap orang sama, mohon konfirmasi (PDF = Posting): " + "; ".join(f"{a['name']} = {p['name']}" for a, p in pairs))
    return "\n".join(L)

if __name__ == "__main__":
    if len(sys.argv) < 3: raise SystemExit("Pakai: crosscheck_pdf.py <attendance.txt> <SC>   (untuk cross-check penuh: dailymp.py --xc)")
    p, st = parse_att(open(sys.argv[1], encoding="utf-8", errors="ignore").read(), sys.argv[2])
    print(f"{len(p)} orang terbaca (tertulis {st})"); [print(f"- {x['name']} | {x['role']} | {x['section']}") for x in p]
