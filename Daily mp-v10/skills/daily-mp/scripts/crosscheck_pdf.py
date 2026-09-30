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
    if not folder or not os.path.isdir(folder): return None
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
        if "|" in line:                                        # format hasil pdf_to_att.py: Nama | Role | PT/CV
            f = [x.strip() for x in line.split("|")] + ["", ""]
            if f[0] and (not f[2] or sc_l in f[2].lower()):
                people.append({"name": re.sub(r"^\d+[\s.)]+", "", f[0]), "role": f[1] or None, "section": section})
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

def rk(x): return nn(x.get("role"))

def crosscheck(att, post, thr=0.82):
    """Urutan: persis > ejaan mirip (>=82%) > nama singkat vs lengkap (role membantu bila ambigu) >
    token mirip pada role sama > mirip lemah (>=70%, saling terbaik, perlu konfirmasi)."""
    ua, up = set(), set()
    out = {"exact": [], "fuzzy": [], "subset": [], "token": [], "weak": []}
    def take(kind, i, j, *extra): out[kind].append((att[i], post[j]) + extra); ua.add(i); up.add(j)
    for i, a in enumerate(att):
        for j, p in enumerate(post):
            if j not in up and nn(a["name"]) == nn(p["name"]): take("exact", i, j); break
    for i, a in enumerate(att):
        if i in ua: continue
        best, bj = 0, None
        for j, p in enumerate(post):
            if j in up: continue
            s = sim(a["name"], p["name"])
            if s > best: best, bj = s, j
        if bj is not None and best >= thr: take("fuzzy", i, bj, best)
    for i, a in enumerate(att):
        if i in ua: continue
        at = toks(a["name"])
        c = [j for j, p in enumerate(post) if j not in up and toks(p["name"]) and (toks(p["name"]) <= at or at <= toks(p["name"]))
             and len(nn(p["name"])) >= (3 if rk(a) and rk(a) == rk(p) else 4)]
        if len(c) > 1: c = [j for j in c if rk(a) and rk(a) == rk(post[j])]
        if len(c) == 1: take("subset", i, c[0])
    for i, a in enumerate(att):
        if i in ua or not rk(a): continue
        for j, p in enumerate(post):
            if j not in up and rk(a) == rk(p) and any(difflib.SequenceMatcher(None, x, y).ratio() >= 0.8 for x in toks(a["name"]) for y in toks(p["name"]) if len(x) > 3 and len(y) > 3):
                take("token", i, j); break
    for i, a in enumerate(att):
        if i in ua: continue
        sc = [(sim(a["name"], p["name"]), j) for j, p in enumerate(post) if j not in up]
        if not sc: continue
        s, j = max(sc)
        back = max((sim(att[k]["name"], post[j]["name"]), k) for k in range(len(att)) if k not in ua)
        if s >= 0.70 and back[1] == i: take("weak", i, j, s)
    out["only_att"] = [a for i, a in enumerate(att) if i not in ua]
    out["only_post"] = [p for j, p in enumerate(post) if j not in up]
    return out

def report(sc, d, att, att_stated, post, post_stated, absent=()):
    r = crosscheck(att, post)
    ab = [{"name": re.sub(r"(?i)\(.*?\)|\babsen\b|[:]", "", str(b)).strip(), "role": None, "section": "absen"} for b in absent]
    ra = crosscheck(r["only_att"], ab) if ab and r["only_att"] else None
    known_absent = [a for k in ("exact", "fuzzy", "subset", "token", "weak") for a, *_ in ra[k]] if ra else []
    only_att = [a for a in r["only_att"] if a not in known_absent]
    f = lambda x: f"{x['name']} ({x['role'] or x['section']})"
    same = len(r["exact"]) + len(r["fuzzy"]) + len(r["subset"]) + len(r["token"])
    L = [f"### Cross-check {sc} {d}: Attendance PDF vs Posting",
         f"PDF {len(att)} orang" + (f" (tertulis {att_stated})" if att_stated else "") + f" | Posting {len(post)} orang (setelah dedup)" +
         (f", tertulis {post_stated}" if post_stated else "") +
         f" | cocok {same} (persis {len(r['exact'])}, ejaan/nama beda {same - len(r['exact'])}), mirip lemah {len(r['weak'])}, "
         f"hanya di PDF {len(only_att)}, hanya di Posting {len(r['only_post'])}"]
    if only_att: L.append(f"- Ada di daftar PDF, tidak di Posting ({len(only_att)}; mungkin hadir tapi tidak tercatat di TBM): " + "; ".join(map(f, only_att)))
    if known_absent: L.append(f"- Ada di PDF dan tercatat ABSEN di Posting ({len(known_absent)}; konsisten): " + "; ".join(map(f, known_absent)))
    if r["only_post"]: L.append(f"- Ada di Posting, tidak di PDF ({len(r['only_post'])}; nama/posisi beda atau tidak ada di daftar): " + "; ".join(map(f, r["only_post"])))
    pairs = [(x[0], x[1]) for k in ("fuzzy", "subset", "token") for x in r[k] if not (k == "fuzzy" and x[2] >= 0.95)]
    if pairs: L.append("- Ejaan/nama beda, dianggap orang sama (PDF = Posting): " + "; ".join(f"{a['name']} = {p['name']}" for a, p in pairs))
    if r["weak"]: L.append("- Mirip lemah, mohon konfirmasi (PDF ? Posting): " + "; ".join(f"{a['name']} ? {p['name']}" for a, p, _ in r["weak"]))
    return "\n".join(L)

if __name__ == "__main__":
    if len(sys.argv) < 3: raise SystemExit("Pakai: crosscheck_pdf.py <attendance.txt> <SC>   (untuk cross-check penuh: dailymp.py --xc)")
    p, st = parse_att(open(sys.argv[1], encoding="utf-8", errors="ignore").read(), sys.argv[2])
    print(f"{len(p)} orang terbaca (tertulis {st})"); [print(f"- {x['name']} | {x['role']} | {x['section']}") for x in p]
