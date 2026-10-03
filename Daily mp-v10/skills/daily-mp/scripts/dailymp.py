#!/usr/bin/env python3
"""Daily MP - rekap manpower harian semua subcontractor (format Excel rekap manpower).

  python dailymp.py --dir /tmp/mp --date 2026-09-28
  python dailymp.py --dir /tmp/mp --date 2026-09-28 --detail
  python dailymp.py --dir /tmp/mp --date 2026-09-28 --xlsx out.xlsx
  python dailymp.py --dir /tmp/mp --summary                 # total per subcontractor per tanggal
  python dailymp.py --dir /tmp/mp --date 2026-09-28 --map "Driver=Staff" --map "Erector=Skilled Workers"

File di --dir harus diawali kode subcontractor: "SILOG TBM 20260928 Posting.txt", "TPE_20260928.txt",
"DJK MP Service 26-28 Sep 2026.txt" (DJK boleh multi-hari), dst.
"""
import re, os, json, argparse, difflib, glob
import datetime
from datetime import date as _date

SUBS = ["SILOG", "TODJO", "DHJ", "WKP", "TPE", "WME", "DJK", "BCP", "BME"]
ALIAS = {"TOHOMA": "TODJO", "TOHOMA-DWIDJO": "TODJO"}
NEW = " (role baru)"

ROWS = [
    ("Indirect", "Project Manager"), ("Indirect", "Deputy Project Manager"),
    ("Indirect", "Construction Manager"), ("Indirect", "Deputy CM"),
    ("Indirect", "Site Engineer"), ("Indirect", "HSE Manager"), ("Indirect", "HSE Engineer"),
    ("Indirect", "Survey Manager"), ("Indirect", "Surveyor"), ("Indirect", "QS Department"),
    ("Indirect", "Engineering Department"), ("Indirect", "QA/QC Department"),
    ("Indirect", "Administration Department"), ("Indirect", "Supervisor"),
    ("Direct", "Foreman"), ("Direct", "Rebarman"), ("Direct", "Carpenter"), ("Direct", "Stone Masonry"),
    ("Direct", "Scaffolder"), ("Direct", "Skilled Workers"), ("Direct", "Common Labor"),
    ("", "Security"), ("Indirect", "Staff"), ("Direct", "Heavy Equipment Operator"),
]
POS = [p for _, p in ROWS]
EXTRA = ["Land 1", "Land 2"]   # baris tambahan khusus DJK, hanya muncul bila ada isinya
SC_MAP = {}; CUR = [None]
TYPE_OF = {p: t for t, p in ROWS}
SUM_ROWS = [("Indirect", "Indirect (tanpa rincian posisi)"), ("Direct", "Direct (tanpa rincian posisi)")]

ROLE_MAP = {
    "pm": "Project Manager", "project manager": "Project Manager",
    "dpm": "Deputy Project Manager", "deputy project manager": "Deputy Project Manager",
    "cm": "Construction Manager", "construction manager": "Construction Manager",
    "dcm": "Deputy CM", "deputy cm": "Deputy CM",
    # SM = Site Manager, sengaja dimasukkan ke Site Engineer (kebijakan user)
    "sm": "Construction Manager", "site manager": "Construction Manager", "se": "Site Engineer",
    "site engineer": "Site Engineer", "engineer": "Site Engineer", "enginer": "Site Engineer",
    "eng": "Site Engineer", "rigging eng": "Site Engineer", "pc": "Site Engineer",
    "ppc": "Site Engineer", "project control": "Site Engineer",
    "hse manager": "HSE Manager",
    "survey manager": "Survey Manager", "surveyor": "Surveyor", "team surveyor": "Surveyor",
    "ass surveyor": "Surveyor", "qs": "QS Department",
    "qc": "QA/QC Department", "qa": "QA/QC Department", "qc lead": "QA/QC Department",
    "admin": "Staff", "docon": "Staff", "document control": "Staff", "document controller": "Staff", "sdcc": "Staff", "hrd": "Staff", "spv hrga": "Staff", "spv hr ga": "Staff", "spv finance": "Staff", "adm project": "Staff",
    "driver": "Common Labor", "housekeeping": "Common Labor", "hole watcher": "Common Labor", "helper": "Common Labor", "hlp": "Common Labor", "h": "Common Labor",
    "safety officer": "HSE Engineer", "admin hse": "HSE Engineer", "hse officer": "HSE Engineer", "hse coordinator": "HSE Engineer",
    "field engineer": "Site Engineer", "planning engineer": "Site Engineer", "piping engineer": "Site Engineer", "planning eng": "Site Engineer", "piping eng": "Site Engineer", "lifting eng": "Site Engineer",
    "ass survey": "Surveyor", "assistan surveyor": "Surveyor", "survey": "Surveyor", "admin qc": "QA/QC Department", "welding inspector": "QA/QC Department", "weld inspect": "QA/QC Department", "qc field": "QA/QC Department",
    "mandor": "Foreman", "inspector scaffolder": "Scaffolder", "helper scaffolder": "Scaffolder", "foreman scaffolder": "Scaffolder", "helper scf": "Scaffolder",
    "skill matecon": "Skilled Workers", "skill matcon": "Skilled Workers", "skill logistic": "Skilled Workers", "skill other": "Skilled Workers", "fm other": "Foreman",
    "erector": "Skilled Workers", "civil": "Skilled Workers", "millright": "Skilled Workers", "mekanik": "Skilled Workers", "wiring": "Skilled Workers", "busbar": "Skilled Workers", "checker": "Skilled Workers", "worker": "Skilled Workers", "electric": "Skilled Workers",
    "opr crane": "Heavy Equipment Operator", "opr tmc": "Heavy Equipment Operator",
    "matecon": "Staff", "matkon": "Staff", "material control": "Staff",
    "spv": "Supervisor", "supervisor": "Supervisor",
    "foreman": "Foreman", "foremen": "Foreman", "formen": "Foreman", "fm": "Foreman",
    "si": "Foreman",  # SI = Subcontractor Independen
    "rebarman": "Rebarman", "carpenter": "Carpenter", "stone masonry": "Stone Masonry", "mason": "Stone Masonry",
    "scaffolder": "Scaffolder", "scf": "Scaffolder", "insp scaffolding": "Scaffolder",
    "inspector scaffolding": "Scaffolder", "inspektor scaffolder": "Scaffolder", "inspector scf": "Scaffolder",
    "teknisi": "Skilled Workers", "technician": "Skilled Workers", "rigger": "Skilled Workers",
    "welder": "Skilled Workers", "skill": "Skilled Workers", "skil": "Skilled Workers",
    "fitter": "Skilled Workers",
    "ft": "Skilled Workers", "mw": "Skilled Workers", "mep": "Skilled Workers",
    "f": "Skilled Workers",
    "security": "Security",
}
# seksi -> posisi (dipakai untuk orang tanpa role). "team qc" memaksa semua anggota jadi QA/QC.
SECTION_RULES = [("scaffold", "Scaffolder"), ("surveyor", "Surveyor"), ("warehouse", "Common Labor"),
                 ("hole watcher", "Common Labor"), ("mechanical fitter", "Skilled Workers"), ("welder", "Skilled Workers"),
                 ("rigger", "Skilled Workers"), ("electri", "Skilled Workers"), ("operator", "Heavy Equipment Operator")]
ABSENT_RE = re.compile(r"\b(absen|sakit|izin|cuti|alpa)\b", re.I)
OVERRIDES = {}
PDF_PRIMARY = ("WME", "WKP", "BCP")   # sumber utama = Attendance PDF; Posting hanya cek jumlah
ATT_DIR = [None]; DEDUP_THR = [0.85]; DEDUP_SCOPE = ["section"]; WARN = {}
DAYS = {"senin":0,"selasa":1,"rabu":2,"kamis":3,"jumat":4,"jum'at":4,"sabtu":5,"minggu":6,"monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4,"saturday":5,"sunday":6}
NAMA_HARI = ["Senin","Selasa","Rabu","Kamis","Jumat","Sabtu","Minggu"]
MON = {"jan":1,"feb":2,"mar":3,"apr":4,"mei":5,"may":5,"jun":6,"jul":7,"agu":8,"aug":8,"sep":9,"okt":10,"oct":10,"nov":11,"des":12,"dec":12}

def load_extra():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "roles.json")
    if os.path.exists(p):
        try:
            for k, v in json.load(open(p, encoding="utf-8")).get("role_map", {}).items():
                OVERRIDES[norm(k)] = v
        except Exception:
            pass

def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[_.\-/]+", " ", (s or "").lower())).strip()

def clean(text):
    text = re.sub(r"[\u200b-\u200f\u2060\ufeff]", "", text).replace("\\", "")
    return re.sub(r"(?<=[^\s\d\n])(\d{1,3}\s*\.\s)", r"\n\1", text)   # item yang menempel jadi baris baru

def label_new(txt):
    txt = re.sub(r"\(.*?\)", "", txt).strip(" :*-")
    if not any(ch.isdigit() for ch in txt) and (txt.islower() or (txt.isupper() and len(txt) > 4)):
        txt = txt.title()
    return (txt or "Tanpa role") + NEW

def load_scmap():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sc_map.json")
    if os.path.exists(p): SC_MAP.update(json.load(open(p, encoding="utf-8")))

def classify(role, section):
    """Urutan: --map/roles.json > aturan DJK > pemetaan per-SC (sc_map.json) > aturan umum > role baru."""
    r, s = norm(role), norm(section)
    r = re.sub(r"^hlp\b", "helper", r)
    for k, pos in SC_MAP.get("_forced", {}).get(CUR[0], {}).items():   # seksi yang memaksa posisi (mis. Team QC di SILOG)
        if k in s: return pos
    for key in (r, s):
        if key and key in OVERRIDES: return OVERRIDES[key]
    if CUR[0] == "DJK":
        if r.startswith(("spv", "supervisor")) or s.startswith("spv"): return "Supervisor"
        return "Land 2" if "warehouse" in s else "Land 1"
    m = SC_MAP.get(CUR[0], {})
    if r.startswith("helper") and "warehouse" in s: return "Common Labor"
    if r:
        for tbl in (m, ROLE_MAP):
            if r in tbl: return tbl[r]
        if r.startswith(("spv", "supervisor")): return "Supervisor"
        if "hse" in r.split() or r.startswith("hse"): return "HSE Manager" if "manager" in r else "HSE Engineer"
        if r.startswith("operator"): return "Heavy Equipment Operator"
        if r.startswith("helper"): return "Common Labor"
        if r.startswith("fm"): return "Foreman"
        if "insp" in r and ("scaf" in r or "scf" in r): return "Scaffolder"
        if r.startswith(("qc", "qa")): return "QA/QC Department"
        return label_new(role)
    secs = SC_MAP.get("_sections")
    rules = ({**secs.get("_default", {}), **secs.get(CUR[0], {})} if secs else dict(SECTION_RULES))
    for sub, pos in rules.items():
        if sub in s: return pos
    for tbl in (m, ROLE_MAP):
        if s in tbl: return tbl[s]
    return label_new(section)

# ---------------------------------------------------------------- parser
def find_stated(text):
    m = re.search(r"(?i)total\s*(?:all|manpower|mp|aktif)\s*[:=]?\s*(\d+)", text)
    return int(m.group(1)) if m else None

def mk(section, role, name):
    return {"section": section, "role": role, "name": name, "category": classify(role, section)}

def split_item(body):
    """'Role : Name' | 'Name ( Role )' | 'Name' -> (role, name)"""
    if ":" in body:
        r, n = body.split(":", 1); return (r.strip() or None), n.strip()
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", body)
    if m: return (m.group(2).strip() or None), m.group(1).strip()
    return None, body.strip()

def parse_numbered(text):
    people, absent, section, off = [], [], "Manpower", False
    for raw in clean(text).splitlines():
        line = raw.strip()
        if not line: continue
        if re.match(r"(?i)^[-*•\s]*total\b", line): break
        if re.match(r"(?i)^(area\b|supporting team|plan\b|kondisi|cuaca|work description|weather|loc\.)", line): break
        item = re.match(r"^\d+\s*[.)]\s*(.*)$", line)
        if item:
            body = item.group(1).strip()
            if not body: continue
            if off or ABSENT_RE.search(body):
                absent.append(body); continue
            role, name = split_item(body)
            if name: people.append(mk(section, role, name))
            continue
        hdr = re.match(r"(?i)^(.+?)\s*:\s*\d+\s*person", line)
        if hdr:
            section, off = hdr.group(1).strip(), False; continue
        head = re.match(r"^[*•\-]\s*(.+)$", line)
        if head and not re.match(r"(?i)^crew", head.group(1)):
            section = head.group(1).strip(" :*"); off = norm(section).startswith("off")
    return people, absent

def parse_dhj(text):
    people, role, on = [], None, False
    for raw in clean(text).splitlines():
        line = raw.strip()
        if re.match(r"(?i)^man\s*power", line): on = True; continue
        if not on: continue
        if re.match(r"(?i)^(total|plan|kondisi)", line): break
        m = re.match(r"^([^=]*?)\s*=\s*(.*)$", line)
        if not m: continue
        if m.group(1).strip(): role = m.group(1).strip()
        if m.group(2).strip(): people.append(mk("Man Power", role, m.group(2).strip()))
    return people, []

def parse_todjo(text):
    people, absent, mode = [], [], None
    for raw in clean(text).splitlines():
        line = re.sub(r"^[.\s]+", "", raw.strip())
        if not line: continue
        if re.match(r"(?i)^total", line) or re.match(r"(?i)^work description", line): break
        if re.match(r"(?i)^man\s*power", line): mode = "staff"; continue
        if re.match(r"(?i)^crew", line): mode = "crew"; continue
        if re.match(r"(?i)^tidak\s+berangkat", line): mode = "absent"; continue
        if mode is None: continue
        if mode == "staff" and ":" in line:
            r, n = line.split(":", 1)
            if n.strip(): people.append(mk("Staff", r.strip(), n.strip()))
        elif mode in ("crew", "absent"):
            role, name = split_item(line)
            if not name: continue
            (absent if mode == "absent" else people).append(name if mode == "absent" else mk("Crew", role, name))
    return people, absent

def parse_summary(text):
    t = clean(text); out = {}
    for key, pat in (("indirect", r"indirect\s*[=:]\s*(\d+)"), ("direct", r"(?<!in)direct\s*[=:]\s*(\d+)"),
                     ("staff", r"staf+\s*[:=]\s*(\d+)"), ("worker", r"worker\s*[:=]\s*(\d+)"),
                     ("total", r"total\s*(?:mp|manpower)\s*[:=]?\s*(\d+)")):
        m = re.search(pat, t, re.I)
        if m: out[key] = int(m.group(1))
    ind = out.get("indirect", out.get("staff")); dr = out.get("direct", out.get("worker"))
    return {"indirect": ind, "direct": dr, "total": out.get("total")} if (ind is not None or dr is not None) else None

def parse_djk(text):
    days = {}
    for block in re.split(r"(?=TBM PAGI)", text):
        m = re.search(r"(?i)(senin|selasa|rabu|rabo|kamis|jumat|sabtu|minggu)\s+(\d{1,2})-(\d{1,2})-(\d{4})", block)
        if not m: continue
        d = f"{m.group(4)}-{int(m.group(3)):02d}-{int(m.group(2)):02d}"
        p, a = parse_numbered(block)
        days[d] = (p, a, find_stated(block))
    return days

# ---------------------------------------------------------------- dedupe
def nn(s): return re.sub(r"[^a-z]", "", (s or "").lower())
def nr(r):
    r = norm(r)
    return {"foremen": "foreman", "formen": "foreman", "fm": "foreman"}.get(r, r)

def dedupe(people):
    """Aturan: (1) nama & posisi sama = hapus. (2) nama mirip >= ambang di kategori sama = hapus; bila scope 'section',
    hanya jika di seksi/lokasi yang sama (lintas lokasi = kemungkinan orang berbeda, hanya diberi peringatan).
    (3) mirip tapi tidak dihapus dan nama sama beda posisi = peringatan cek manual."""
    thr, scope = DEDUP_THR[0], DEDUP_SCOPE[0]
    removed, kept, seen = [], [], set()
    for p in people:
        k = (nn(p["name"]), nr(p["role"]), p["category"])
        if k in seen: removed.append((p, "nama & posisi sama")); continue
        seen.add(k); kept.append(p)
    final, near = [], []
    for b in kept:
        hit = None
        for i, a in enumerate(final):
            if a["category"] != b["category"] or nn(a["name"]) == nn(b["name"]): continue
            r = difflib.SequenceMatcher(None, nn(a["name"]), nn(b["name"])).ratio()
            if r >= thr:
                if scope == "section" and norm(a["section"]) != norm(b["section"]): near.append((a, b, r, "lintas lokasi")); continue
                hit = i; break
            if r >= thr - 0.05: near.append((a, b, r, ""))
        if hit is None: final.append(b)
        else:
            a = final[hit]
            if a["role"] is None and b["role"]:
                final[hit] = b; removed.append((a, f"ejaan mirip dengan {b['name']}"))
            else: removed.append((b, f"ejaan mirip dengan {a['name']}"))
    warns, by = [], {}
    for p in final: by.setdefault(nn(p["name"]), []).append(p)
    for v in by.values():
        if len(v) > 1:
            warns.append("nama sama, posisi beda (tidak dihapus, cek manual): " +
                         "; ".join(f"{x['name']} - {x['role'] or x['section']}" for x in v))
    for a, b, r, tag in near:
        if nn(a["name"]) in by and len(by[nn(a["name"])]) > 1: continue
        warns.append(f"nama mirip {r:.0%} (tidak dihapus{', ' + tag if tag else ''}, cek manual): "
                     f"{a['name']} [{a['section']}] ~ {b['name']} [{b['section']}]")
    return final, removed, warns

# ---------------------------------------------------------------- load
def sub_of(fname):
    tok = re.split(r"[\s_\-]", os.path.basename(fname).upper())[0]
    tok = ALIAS.get(tok, tok)
    return tok if tok in SUBS else None

def check_header(text, d):
    """Peringatan: hari tidak cocok dengan tanggal, atau tanggal header beda dengan nama file."""
    m = re.search(r"(?i)\b(senin|selasa|rabu|kamis|jum'?at|sabtu|minggu|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\W{1,3}(\d{1,2})\s+([a-z]+)\s+(20\d{2})", text[:600])
    if not m:
        m2 = re.search(r"(?i)\b(\d{1,2})\s+([a-z]{3,9})\s+(20\d{2})", text[:300])
        if not m2 or not MON.get(m2.group(2).lower()[:3]): return []
        try: hd = datetime.date(int(m2.group(3)), MON[m2.group(2).lower()[:3]], int(m2.group(1)))
        except ValueError: return []
        return [] if hd.isoformat() == d else [f"tanggal di header ({hd.isoformat()}) beda dengan tanggal di nama file ({d}), kemungkinan data lama atau rencana hari lain"]
    mon = MON.get(m.group(3).lower()[:3])
    try: hd = datetime.date(int(m.group(4)), mon, int(m.group(2)))
    except (TypeError, ValueError): return []
    w = []
    if hd.weekday() != DAYS[m.group(1).lower()]:
        w.append(f"header menulis '{m.group(0).strip()}' tetapi {hd.isoformat()} jatuh pada hari {NAMA_HARI[hd.weekday()]}")
    if hd.isoformat() != d: w.append(f"tanggal di header ({hd.isoformat()}) beda dengan tanggal di nama file ({d})")
    return w

def numbering_warnings(text):
    """Nomor urut loncat atau baris tanpa nama = daftar nama kemungkinan tidak lengkap (mis. TPE)."""
    sec, nums, blanks, w = "Manpower", {}, {}, []
    for raw in clean(text).splitlines():
        line = raw.strip()
        if re.match(r"(?i)^[-*•\s]*total\b", line) or re.match(r"(?i)^(area\b|supporting team|plan\b|kondisi|cuaca|work description|weather|loc\.)", line): break
        it = re.match(r"^(\d+)\s*[.)]\s*(.*)$", line)
        if it:
            body = it.group(2).strip(); nums.setdefault(sec, []).append(int(it.group(1)))
            role, name = split_item(body) if body else (None, "")
            if not name: blanks.setdefault(sec, []).append(role or "?")
            continue
        hdr = re.match(r"(?i)^(.+?)\s*:\s*\d+\s*person", line)
        if hdr: sec = hdr.group(1).strip(); continue
        head = re.match(r"^[*•\-]\s*(.+)$", line)
        if head and not re.match(r"(?i)^crew", head.group(1)): sec = head.group(1).strip(" :*")
    for k, ns in nums.items():
        miss = sorted(set(range(1, max(ns) + 1)) - set(ns))
        if len(miss) >= 2: w.append(f"seksi {k}: nomor urut loncat ({len(miss)} nomor tidak ada, mis. {', '.join(map(str, miss[:5]))}), daftar nama mungkin tidak lengkap")
    for k, rs in blanks.items(): w.append(f"seksi {k}: {len(rs)} baris tanpa nama ({', '.join(rs)})")
    return w

def load_dir(folder):
    res = {s: {} for s in SUBS}
    for f in sorted(glob.glob(os.path.join(folder, "*"))):
        sub = sub_of(f)
        if not sub: continue
        CUR[0] = sub
        if f.lower().endswith(".pdf"):
            m = re.search(r"(20\d{2})(\d{2})(\d{2})", f)
            if m: res[sub].setdefault(f"{m.group(1)}-{m.group(2)}-{m.group(3)}", {"status": "pdf", "file": os.path.basename(f)})
            continue
        if "attendance" in os.path.basename(f).lower(): continue   # Attendance .txt hanya untuk cross-check
        text = open(f, encoding="utf-8", errors="ignore").read()
        if sub == "DJK":
            for d, (p, a, st) in parse_djk(text).items():
                res[sub][d] = {"status": "ok", "people": p, "absent": a, "stated": st, "file": os.path.basename(f)}
            continue
        m = re.search(r"(20\d{2})(\d{2})(\d{2})", os.path.basename(f))
        if not m: continue
        d = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        if not text.strip():
            res[sub][d] = {"status": "empty", "file": os.path.basename(f)}; continue
        WARN[(sub, d)] = check_header(text, d) + (numbering_warnings(text) if sub not in ("DHJ", "TODJO", "WME", "WKP") else [])
        if sub in ("WME", "WKP"):
            s = parse_summary(text)
            res[sub][d] = {"status": "summary", "summary": s, "file": os.path.basename(f)} if s else \
                          {"status": "unknown", "file": os.path.basename(f)}
            continue
        fn = {"DHJ": parse_dhj, "TODJO": parse_todjo}.get(sub, parse_numbered)
        p, a = fn(text)
        res[sub][d] = ({"status": "ok", "people": p, "absent": a, "stated": find_stated(text), "file": os.path.basename(f)}
                       if p else {"status": "unknown", "file": os.path.basename(f)})
    return res

# ---------------------------------------------------------------- report
def pdf_source(s, d, r):
    """SC bersumber PDF: hitung per posisi dari <SC>_<tgl>_Attendance.txt, bandingkan jumlahnya dengan Posting."""
    import crosscheck_pdf as X
    f = X.find_attendance(ATT_DIR[0], s, d)
    if not f: return None
    with open(f, encoding="utf-8", errors="ignore") as source:
        people, _ = X.parse_att(source.read(), s)
    if not people:
        return None, [f"⚠ **{s}**: Attendance file ditemukan tetapi tidak ada baris roster yang terbaca; hasil bukan 0 orang. Periksa PDF/OCR sebelum memakai angka."], {}
    CUR[0] = s; counts, newr, tp = {}, {}, {"Indirect": 0, "Direct": 0}
    tipe = {p: t for t, p in ROWS}
    for p in people:
        cat = classify(p["role"], p["section"]); counts[cat] = counts.get(cat, 0) + 1
        if cat not in POS and cat not in EXTRA: newr.setdefault(cat, []).append(p["name"])
        if tipe.get(cat) in tp: tp[tipe[cat]] += 1
    n = [f"**{s}**: {len(people)} orang dari PDF Attendance (roster; tanda tangan tidak terbaca, jadi ini batas atas kehadiran)"]
    if r and r["status"] == "summary":
        sm = r["summary"]; tot = sm["total"] or (sm["indirect"] or 0) + (sm["direct"] or 0)
        n.append(f"Posting: Indirect {sm['indirect']}, Direct {sm['direct']}, Total {tot} | PDF: Indirect {tp['Indirect']}, Direct {tp['Direct']}, Total {len(people)} (selisih total {len(people) - tot:+d})")
    else: n.append("Posting tidak ada/tanpa total, jumlah tidak bisa dicek")
    return counts, [" | ".join(n)] + [f"⚠ **{s}**: {x}" for x in WARN.get((s, d), [])], newr

def build(res, d, detail):
    cols, notes, newroles = {}, [], {}
    for s in SUBS:
        r = res[s].get(d)
        if s in PDF_PRIMARY and ATT_DIR[0]:
            got = pdf_source(s, d, r)
            if got:
                if got[0] is None:
                    cols[s] = ("missing", None); notes += got[1]
                    continue
                cols[s] = ("ok", got[0]); notes += got[1]
                for k, v in got[2].items(): newroles.setdefault(k, {}).setdefault(s, []).extend(v)
                continue
            notes.append(f"⚠ **{s}**: sumber utama adalah PDF Attendance tetapi {s}_{d.replace('-', '')}_Attendance.txt belum ada; jalankan pdf_to_att.py atau unggah PDF ke chat. Angka di bawah hanya dari Posting.")
        if not r:
            cols[s] = ("missing", None); notes.append(f"**{s}**: belum ada data untuk {d}."); continue
        if r["status"] == "pdf":
            cols[s] = ("missing", None)
            notes.append(f"**{s}**: hanya ada PDF foto absensi ({r['file']}), tidak dibaca otomatis. Kirim Posting.txt agar bisa direkap."); continue
        if r["status"] == "empty":
            cols[s] = ("missing", None); notes.append(f"**{s}**: file {r['file']} kosong (0 byte), belum diisi atau perlu diunggah ulang."); continue
        for x in WARN.get((s, d), []): notes.append(f"⚠ **{s}**: {x}")
        if r["status"] == "unknown":
            cols[s] = ("missing", None); notes.append(f"**{s}**: format {r['file']} tidak dikenali."); continue
        if r["status"] == "summary":
            sm = r["summary"]; cols[s] = ("summary", sm)
            prev = sorted(x for x in res[s] if x < d)
            if prev and res[s][prev[-1]].get("summary") == sm:
                notes.append(f"⚠ **{s}**: total sama persis dengan {prev[-1]} (Indirect {sm['indirect']}, Direct {sm['direct']}), kemungkinan salinan hari sebelumnya.")
            notes.append(f"**{s}**: laporan hanya berisi total (Indirect {sm['indirect']}, Direct {sm['direct']}"
                         f"{', Total ' + str(sm['total']) if sm['total'] else ''}), tanpa rincian posisi. Ditaruh di baris 'tanpa rincian posisi'.")
            continue
        people, removed, warns = dedupe(r["people"])
        counts = {}
        for p in people: counts[p["category"]] = counts.get(p["category"], 0) + 1
        cols[s] = ("ok", counts)
        n = [f"**{s}**: {len(people)} orang"]
        if r["stated"] is not None and r["stated"] != len(people):
            n.append(f"total di teks {r['stated']} (selisih {len(people) - r['stated']:+d})")
        if r["stated"] is None: n.append("total di teks tidak ditemukan")
        if r["absent"]: n.append(f"{len(r['absent'])} tidak hadir dikeluarkan")
        if s == "SILOG" and any(norm(p["role"]) == "sm" for p in people): n.append("SM (Site Manager) masuk Site Engineer")
        if any(norm(p["role"]) == "si" for p in people): n.append("SI (Subcontractor Independen) masuk Foreman")
        if removed:
            n.append(f"{len(removed)} double dihapus: " + "; ".join(f"{p['name']} [{w}]" for p, w in removed))
        n += warns
        notes.append(" | ".join(n))
        for p in people:
            if p["category"] not in POS and p["category"] not in EXTRA:
                newroles.setdefault(p["category"], {}).setdefault(s, []).append(p["name"])
        if detail:
            det = {}
            for p in people: det.setdefault(p["category"], []).append(p["name"])
            notes.append(f"  Rincian {s}: " + "; ".join(f"{k} ({len(v)}): {', '.join(v)}" for k, v in det.items()))
    rows_def = list(ROWS)
    if any(k == "summary" for k, _ in cols.values()): rows_def += SUM_ROWS
    for e in EXTRA:
        if any(k == "ok" and e in d for k, d in cols.values()): rows_def.append(("", e))
    for nr_label in newroles: rows_def.append(("", nr_label))
    table = []
    for t, p in rows_def:
        vals = []
        for s in SUBS:
            kind, data = cols[s]
            if kind == "missing": vals.append("n/a")
            elif kind == "summary":
                vals.append(data["indirect"] if p == SUM_ROWS[0][1] and data["indirect"] is not None else
                            data["direct"] if p == SUM_ROWS[1][1] and data["direct"] is not None else "-")
            else: vals.append(data.get(p, 0))
        table.append((t, p, vals))
    return table, notes, newroles

def total(vals): return sum(v for v in vals if isinstance(v, int))
def col_totals(table): return [total([r[2][i] for r in table]) for i in range(len(SUBS))]
def has_data(table): return any(isinstance(v, int) for _, _, vals in table for v in vals)

def md_compact(table, d, res):
    """Tabel ringkas untuk chat: hanya kolom SC yang ada data dan baris yang tidak nol."""
    if not has_data(table): return f"## Daily MP - {d}\n\nBelum ada data untuk seluruh subcon: {', '.join(SUBS)}"
    keep = [i for i in range(len(SUBS)) if any(isinstance(r[2][i], int) or r[2][i] == "-" for r in table)]
    rows = [(t, p, [v[i] for i in keep]) for t, p, v in table if any(isinstance(v[i], int) and v[i] for i in keep)]
    head = "| Tipe | Posisi | " + " | ".join(SUBS[i] for i in keep) + " | Total |"
    out = [f"## Daily MP - {d}", "", head, "|---|---|" + "---:|" * (len(keep) + 1)]
    out += [f"| {t} | {p} | " + " | ".join(str(x) for x in v) + f" | {total(v)} |" for t, p, v in rows]
    ct = col_totals(table)
    out.append("| | **Total Manpower** | " + " | ".join(f"**{ct[i]}**" for i in keep) + f" | **{sum(ct)}** |")
    absent = [SUBS[i] for i in range(len(SUBS)) if i not in keep]
    if absent: out.append(f"\nBelum ada data: {', '.join(absent)}")
    return "\n".join(out)

def md(table, d):
    if not has_data(table): return f"## Daily MP - {d}\n\nBelum ada data untuk seluruh subcon: {', '.join(SUBS)}"
    head = "| Tipe | Posisi | " + " | ".join(SUBS) + " | Total |"
    out = [f"## Daily MP - {d}", "", head, "|---|---|" + "---:|" * (len(SUBS) + 1)]
    for t, p, v in table:
        out.append(f"| {t} | {p} | " + " | ".join(str(x) for x in v) + f" | {total(v)} |")
    ct = col_totals(table)
    out.append("| | **Total Manpower** | " + " | ".join(f"**{x}**" for x in ct) + f" | **{sum(ct)}** |")
    return "\n".join(out)

def tsv(table):
    if not has_data(table): return "Belum ada data untuk seluruh subcon: " + ", ".join(SUBS)
    lines = ["\t".join(["Tipe", "Posisi"] + SUBS + ["Total"])]
    for t, p, v in table: lines.append("\t".join([t, p] + [str(x) for x in v] + [str(total(v))]))
    ct = col_totals(table)
    lines.append("\t".join(["", "Total Manpower"] + [str(x) for x in ct] + [str(sum(ct))]))
    return "\n".join(lines)

def to_xlsx(path, table, d, lines=()):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter as L
    wb = Workbook(); ws = wb.active; ws.title = "Daily MP"
    ws.append([f"Daily MP - {d}"]); ws["A1"].font = Font(bold=True, size=13)
    ws.append(["Tipe", "Posisi"] + SUBS + ["Total"])
    for c in ws[2]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="305496"); c.alignment = Alignment(horizontal="center")
    first = 3
    for i, (t, p, v) in enumerate(table):
        r = first + i
        ws.append([t, p] + v + [f"=SUM(C{r}:{L(2 + len(SUBS))}{r})"])
    last = first + len(table) - 1
    ws.append(["", "Total Manpower"] + [f"=SUM({L(3 + i)}{first}:{L(3 + i)}{last})" for i in range(len(SUBS) + 1)])
    for c in ws[ws.max_row]: c.font = Font(bold=True)
    ws.column_dimensions["A"].width = 11; ws.column_dimensions["B"].width = 34
    for i in range(len(SUBS) + 1): ws.column_dimensions[L(3 + i)].width = 9
    ws.freeze_panes = "C3"
    wn = wb.create_sheet("Catatan"); wn.column_dimensions["A"].width = 150
    wn.append([f"Catatan Daily MP {d}"]); wn["A1"].font = Font(bold=True, size=13)
    for ln in lines: wn.append([ln])
    wb.save(path)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True); ap.add_argument("--date")
    ap.add_argument("--detail", action="store_true"); ap.add_argument("--xlsx", nargs="?", const="AUTO")
    ap.add_argument("--summary", action="store_true"); ap.add_argument("--map", action="append", default=[])
    ap.add_argument("--range", nargs=2, metavar=("DARI", "SAMPAI"), help="rentang tanggal YYYY-MM-DD: ringkasan + Excel per hari bila --xlsx")
    ap.add_argument("--compact", action="store_true", help="tabel ringkas untuk chat (tanpa kolom/baris kosong dan tanpa blok TSV)")
    ap.add_argument("--xc", action="store_true", help="cross-check dengan Attendance .txt (SILOG, TPE, DHJ)")
    ap.add_argument("--att-dir", help="folder file Attendance .txt (default: sama dengan --dir)")
    ap.add_argument("--dedup-threshold", type=float, default=0.85)
    ap.add_argument("--dedup-scope", choices=["section", "category"], default="section")
    a = ap.parse_args()
    ATT_DIR[0] = a.att_dir or a.dir; DEDUP_THR[0] = a.dedup_threshold; DEDUP_SCOPE[0] = a.dedup_scope
    load_extra(); load_scmap()
    for m in a.map:
        k, v = m.split("=", 1)
        v = next((p for p in POS if p.lower() == v.strip().lower()), None)
        if not v: raise SystemExit(f"Posisi tidak dikenal di --map: {m}. Pilih salah satu: {', '.join(POS)}")
        OVERRIDES[norm(k)] = v
    res = load_dir(a.dir)
    dates = sorted({d for s in SUBS for d in res[s]})
    if a.summary:
        if not dates:
            print("Tidak ada data tanggal untuk diringkas.")
            raise SystemExit
        print("| Tanggal | " + " | ".join(SUBS) + " | Total |\n|---|" + "---:|" * (len(SUBS) + 1))
        for d in dates:
            table, _, _ = build(res, d, False); ct = col_totals(table)
            grand = sum(ct) if has_data(table) else "n/a"
            print(f"| {d} | " + " | ".join(str(x) if res[s].get(d) and res[s][d]["status"] in ("ok", "summary") else "n/a"
                                               for s, x in zip(SUBS, ct)) + f" | {grand} |")
        raise SystemExit
    if a.range:
        sel = [x for x in dates if a.range[0] <= x <= a.range[1]]
        if not sel:
            print(f"Tidak ada data tanggal dalam rentang {a.range[0]} sampai {a.range[1]}.")
            raise SystemExit
        xlsx_count = 0
        print("| Tanggal | " + " | ".join(SUBS) + " | Total |\n|---|" + "---:|" * (len(SUBS) + 1))
        for x in sel:
            table, notes, _ = build(res, x, False); ct = col_totals(table)
            available = has_data(table)
            grand = sum(ct) if available else "n/a"
            print(f"| {x} | " + " | ".join(str(v) if res[s].get(x) and res[s][x]["status"] in ("ok", "summary") else "n/a" for s, v in zip(SUBS, ct)) + f" | {grand} |")
            for n in notes:
                if "⚠" in n or "kosong" in n: print(f"  - {x}: {n.replace('**', '')}")
            if a.xlsx and available:
                out = os.path.join("/mnt/user-data/outputs" if os.path.isdir("/mnt/user-data/outputs") else ".", f"Daily_MP_{x.replace('-', '')}.xlsx")
                to_xlsx(out, table, x, [n.replace("**", "") for n in notes])
                xlsx_count += 1
            elif a.xlsx:
                print(f"  - {x}: Excel tidak dibuat karena tidak ada data manpower yang terbaca.")
        if a.xlsx: print(f"\nExcel per hari ditulis untuk {xlsx_count} dari {len(sel)} tanggal.")
        raise SystemExit
    d = a.date or (dates[-1] if dates else None)
    if not d: raise SystemExit("Tidak ada file data di folder.")
    table, notes, newroles = build(res, d, a.detail)
    print(md_compact(table, d, res) if a.compact else md(table, d)); print("\n**Catatan:**"); [print("- " + n) for n in notes]
    if newroles:
        print("\n**PERLU KONFIRMASI - role baru (belum ada di aturan), sementara ditaruh di baris sendiri:**")
        for lab, subs in newroles.items():
            print(f"- {lab.replace(NEW, '')}: " + "; ".join(f"{s} ({len(n)}: {', '.join(n)})" for s, n in subs.items()))
        print("Tanyakan ke user masuk posisi mana untuk tiap role di atas. Jangan menebak.")
    xc = []
    if a.xc:
        import crosscheck_pdf as X
        for sc in ("SILOG", "TPE", "DHJ"):
            r = res[sc].get(d)
            if not r or r["status"] != "ok": continue
            f = X.find_attendance(a.att_dir or a.dir, sc, d)
            if not f: xc.append(f"**{sc}**: file Attendance {sc}_{d.replace('-', '')}_Attendance.txt tidak ditemukan, cross-check dilewati."); continue
            att, ast = X.parse_att(open(f, encoding="utf-8", errors="ignore").read(), sc)
            xc.append(X.report(sc, d, att, ast, dedupe(r["people"])[0], r["stated"], r["absent"]))
        print("\n" + "\n\n".join(xc))
    if not a.compact: print("\n### Blok TSV (copy, paste ke Excel)\n\n```\n" + tsv(table) + "\n```")
    if a.xlsx and has_data(table):
        path = a.xlsx if a.xlsx != "AUTO" else os.path.join("/mnt/user-data/outputs" if os.path.isdir("/mnt/user-data/outputs") else ".", f"Daily_MP_{d.replace('-', '')}.xlsx")
        to_xlsx(path, table, d, [n.replace("**", "") for n in notes] + [x.replace("**", "").replace("### ", "") for x in xc]); print(f"\nExcel: {path}")
    elif a.xlsx:
        print("\nExcel tidak dibuat karena tidak ada data manpower yang terbaca.")
