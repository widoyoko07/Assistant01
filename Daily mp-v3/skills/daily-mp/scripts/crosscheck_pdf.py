#!/usr/bin/env python3
"""
Cross-check Attendance PDF (teks OCR dari Google Drive contentSnippet / read_file_content)
dengan hasil rekap Posting.txt SILOG.

Input  : teks OCR dari PDF (copy-paste atau read_file_content), disimpan sebagai .txt
Output : laporan cross-check dalam Markdown

Pakai:
  python crosscheck_pdf.py attendance.txt posting_parsed.json
  python crosscheck_pdf.py attendance.txt posting_parsed.json --md
"""

import re, sys, json, argparse, difflib

# ── helper ──────────────────────────────────────────────────────────────────
def nn(s): return re.sub(r"[^a-z]", "", (s or "").lower())
def similar(a, b): return difflib.SequenceMatcher(None, nn(a), nn(b)).ratio()

OWJJ_ROLES = {"fe", "qc owjj", "owjj"}   # pihak OWJJ, bukan SILOG, skip

def clean(text):
    text = re.sub(r"[\u200b-\u200f\u2060\ufeff\\]", "", text)
    # pisah item yang menempel
    text = re.sub(r"(?<=[^\s\d\n])(\d{1,3}\s*[.)]\s)", r"\n\1", text)
    return text

# ── parse PDF teks ───────────────────────────────────────────────────────────
def parse_pdf(text):
    """
    PDF SILOG punya format tabel: No | Nama | Posisi | PT/CV | Tanda Tangan
    OCR Google Drive menghasilkan fragmen seperti:
      "1\nMuhaimin\nPM\nSILOG\n1\nAndre\nFE\nOWJJ\n..."
    Kita ambil baris yang di-tag 'SILOG' atau 'SILOG/HMG', skip OWJJ.
    """
    people_pdf = []
    total_stated = None

    # cari "TOTAL MANPOWER" di akhir
    m = re.search(r"(?i)total\s*manpower\s*[:\(]?\s*(\d+)", text)
    if m:
        total_stated = int(m.group(1))

    lines = clean(text).splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # deteksi blok: nomor, lalu nama, lalu posisi, lalu PT/CV
        num = re.match(r"^(\d{1,3})[.)]\s*(.*)$", line)
        if num:
            body = num.group(2).strip()
            # kadang nama dan posisi di baris yang sama, dipisah spasi
            # coba lihat baris berikutnya untuk posisi dan PT/CV
            name = body
            role, ptcv = None, None
            # ambil maks 3 baris berikutnya
            lookahead = []
            for j in range(1, 4):
                if i + j < len(lines):
                    lookahead.append(lines[i + j].strip())

            # pola umum: baris 1=posisi, baris 2=PT/CV
            if lookahead and not re.match(r"^\d+[.)]\s", lookahead[0]):
                role = lookahead[0]
                if len(lookahead) > 1 and not re.match(r"^\d+[.)]\s", lookahead[1]):
                    ptcv = lookahead[1].upper()
                    i += 2
                else:
                    i += 1
            # filter: hanya SILOG atau SILOG/HMG, skip OWJJ
            ptcv_norm = (ptcv or "").upper()
            role_norm = (role or "").lower().strip()
            if "SILOG" in ptcv_norm and role_norm not in OWJJ_ROLES:
                people_pdf.append({"name": name, "role": role, "ptcv": ptcv})
        i += 1

    return people_pdf, total_stated

# ── parse Posting JSON (output --json dari dailymp.py) ──────────────────────
def load_posting(path):
    """Muat hasil rekap posting sebagai list {name, category}."""
    data = json.load(open(path, encoding="utf-8"))
    # format: {file: {counts, total_after_dedupe, stated_total}}
    # Kita butuh daftar nama. Kalau ada key 'people', pakai itu.
    # Jika hanya counts, kita tidak punya nama -> return None
    all_people = []
    for v in data.values():
        if "people" in v:
            all_people.extend(v["people"])
    return all_people if all_people else None

# ── cross-check ──────────────────────────────────────────────────────────────
def crosscheck(pdf_people, posting_people, threshold=0.82):
    """
    Bandingkan dua daftar nama.
    Return: hanya_di_pdf, hanya_di_posting, cocok, mirip
    """
    matched_pdf = set()
    matched_post = set()
    exact = []
    fuzzy = []

    pdf_norm = [(nn(p["name"]), i) for i, p in enumerate(pdf_people)]
    post_norm = [(nn(p["name"]), i) for i, p in enumerate(posting_people)]

    # exact match dulu
    for pn, pi in pdf_norm:
        for on, oi in post_norm:
            if pn == on and pi not in matched_pdf and oi not in matched_post:
                exact.append((pdf_people[pi], posting_people[oi]))
                matched_pdf.add(pi); matched_post.add(oi); break

    # fuzzy untuk sisa
    for pn, pi in pdf_norm:
        if pi in matched_pdf: continue
        best_score, best_oi = 0, None
        for on, oi in post_norm:
            if oi in matched_post: continue
            s = similar(pn, on)
            if s > best_score: best_score, best_oi = s, oi
        if best_score >= threshold and best_oi is not None:
            fuzzy.append((pdf_people[pi], posting_people[best_oi], best_score))
            matched_pdf.add(pi); matched_post.add(best_oi)

    only_pdf = [pdf_people[i] for i in range(len(pdf_people)) if i not in matched_pdf]
    only_post = [posting_people[i] for i in range(len(posting_people)) if i not in matched_post]
    return exact, fuzzy, only_pdf, only_post

# ── render ───────────────────────────────────────────────────────────────────
def render(pdf_people, posting_people, total_pdf, total_post):
    exact, fuzzy, only_pdf, only_post = crosscheck(pdf_people, posting_people)

    lines = ["## Cross-Check: Attendance PDF vs Posting.txt (SILOG)", ""]
    lines.append(f"| | Attendance PDF | Posting.txt |")
    lines.append(f"|---|---|---|")
    lines.append(f"| Total tertulis | {total_pdf if total_pdf else '(tidak ada)'} | {total_post if total_post else '(tidak ada)'} |")
    lines.append(f"| Total terbaca | {len(pdf_people)} | {len(posting_people)} |")
    lines.append(f"| Cocok persis | {len(exact)} | |")
    lines.append(f"| Mirip (ejaan beda) | {len(fuzzy)} | |")
    lines.append(f"| Hanya di PDF | {len(only_pdf)} | |")
    lines.append(f"| Hanya di Posting | {len(only_post)} | |")
    lines.append("")

    if only_pdf:
        lines.append("### Ada di PDF tapi TIDAK di Posting.txt")
        lines.append("_(mungkin hadir tapi lupa dicantumkan di TBM, atau nama berbeda)_")
        lines.append("")
        for p in only_pdf:
            lines.append(f"- {p['name']} ({p['role'] or '-'})")
        lines.append("")

    if only_post:
        lines.append("### Ada di Posting.txt tapi TIDAK di PDF")
        lines.append("_(mungkin hadir tapi tidak tanda tangan, atau tidak datang)_")
        lines.append("")
        for p in only_post:
            lines.append(f"- {p['name']} ({p.get('role') or p.get('category', '-')})")
        lines.append("")

    if fuzzy:
        lines.append("### Nama mirip tapi ejaan beda (kemungkinan orang sama)")
        lines.append("")
        lines.append("| PDF | Posting | Kemiripan |")
        lines.append("|---|---|---|")
        for a, b, s in fuzzy:
            lines.append(f"| {a['name']} | {b['name']} | {s:.0%} |")
        lines.append("")

    return "\n".join(lines)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf_txt", help="file teks OCR dari Attendance PDF")
    ap.add_argument("posting_json", nargs="?", help="output --json dari dailymp.py (opsional)")
    ap.add_argument("--total-post", type=int, help="total dari Posting jika tidak ada JSON")
    ap.add_argument("--post-names", help="nama-nama dari Posting, dipisah newline (opsional)")
    a = ap.parse_args()

    pdf_text = open(a.pdf_txt, encoding="utf-8", errors="ignore").read()
    pdf_people, total_pdf = parse_pdf(pdf_text)

    posting_people = []
    total_post = a.total_post
    if a.posting_json:
        pp = load_posting(a.posting_json)
        if pp: posting_people = pp
    elif a.post_names:
        posting_people = [{"name": n.strip(), "role": None} for n in open(a.post_names).read().splitlines() if n.strip()]

    print(render(pdf_people, posting_people, total_pdf, total_post))
    if not posting_people:
        print("\n_Catatan: tidak ada data Posting untuk dibandingkan. Hasil hanya daftar nama dari PDF._")
        print("\n### Daftar nama dari PDF:")
        for p in pdf_people:
            print(f"- {p['name']} ({p['role'] or '-'})")
