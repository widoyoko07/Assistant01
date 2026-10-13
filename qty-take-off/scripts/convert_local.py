#!/usr/bin/env python3
"""Konversi DWG -> DXF (ACAD2018 ASCII) di LAPTOP user memakai ODA File Converter (gratis).
Jalur paling andal untuk DWG besar. Hasil DXF diunggah ke chat Claude, lalu jalankan takeoff.py seperti biasa.

  python convert_local.py FOLDER_ATAU_FILE.dwg [--out FOLDER_DXF] [--version ACAD2018]

ODA File Converter: https://www.opendesign.com/guestfiles/oda_file_converter (pasang dulu).
Lokasi dicari di: env ODA_BIN, PATH, lalu folder instalasi Windows/macOS/Linux umum."""
import argparse, glob, os, shutil, subprocess, sys, tempfile

CANDIDATES = [
    r"C:\Program Files\ODA\ODAFileConverter*\ODAFileConverter.exe",
    r"C:\Program Files (x86)\ODA\ODAFileConverter*\ODAFileConverter.exe",
    "/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter",
    "/usr/bin/ODAFileConverter", "/opt/ODAFileConverter/ODAFileConverter",
]


def find_oda():
    p = os.environ.get("ODA_BIN")
    if p and os.path.exists(p): return p
    p = shutil.which("ODAFileConverter")
    if p: return p
    for pat in CANDIDATES:
        hits = sorted(glob.glob(pat))
        if hits: return hits[-1]
    return None


def verify(dxf):
    """Baca balik DXF bila ezdxf ada; return (ok, pesan)."""
    if not os.path.exists(dxf) or os.path.getsize(dxf) < 1000: return False, "file hasil tidak ada/terlalu kecil"
    try: import ezdxf
    except ModuleNotFoundError: return True, "ezdxf tidak terpasang, hasil belum diverifikasi (pip install ezdxf)"
    try: ezdxf.readfile(dxf); return True, "terbaca ezdxf"
    except Exception as e: return False, f"ezdxf gagal membaca ({type(e).__name__})"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="file .dwg atau folder berisi .dwg")
    ap.add_argument("--out", help="folder hasil (default: <src>/dxf_out)")
    ap.add_argument("--version", default="ACAD2018", help="versi DXF keluaran (default ACAD2018)")
    a = ap.parse_args()
    oda = find_oda()
    if not oda: sys.exit("ODA File Converter tidak ditemukan. Pasang dulu, atau set env ODA_BIN ke ODAFileConverter(.exe).")
    src = os.path.abspath(a.src)
    if os.path.isfile(src):
        if not src.lower().endswith(".dwg"): sys.exit("File harus berekstensi .dwg")
        files, work = [os.path.basename(src)], tempfile.mkdtemp(); shutil.copy(src, work); base = os.path.dirname(src)
    elif os.path.isdir(src):
        files = sorted(f for f in os.listdir(src) if f.lower().endswith(".dwg")); work = src; base = src
    else: sys.exit(f"Tidak ditemukan: {src}")
    if not files: sys.exit("Tidak ada file .dwg.")
    out = os.path.abspath(a.out or os.path.join(base, "dxf_out")); os.makedirs(out, exist_ok=True)
    # argumen ODA: in_dir out_dir versi_keluaran tipe recurse audit [filter]
    r = subprocess.run([oda, work, out, a.version, "DXF", "0", "1", "*.DWG"], capture_output=True, text=True)
    bad = 0
    for f in files:
        dxf = os.path.join(out, os.path.splitext(f)[0] + ".dxf"); ok, msg = verify(dxf)
        print(f"{'OK  ' if ok else 'GAGAL'} {f} -> {dxf} ({msg})"); bad += (not ok)
    if bad: print(f"\n{bad} file gagal. Keluaran ODA:\n{(r.stderr or r.stdout).strip()[-500:]}", file=sys.stderr)
    else: print(f"\nSelesai. Unggah file DXF dari {out} ke chat Claude.")
    sys.exit(1 if bad else 0)


if __name__ == "__main__": main()
