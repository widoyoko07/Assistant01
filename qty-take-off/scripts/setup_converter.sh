#!/usr/bin/env bash
# Coba menyiapkan converter DWG->DXF (dwg2dxf dari LibreDWG) di sandbox/Linux. Aman dijalankan berulang.
# Pakai: bash scripts/setup_converter.sh      Keluar 0 bila dwg2dxf siap, 1 bila tidak.
# Catatan: paket distro belum tentu sanggup membaca DWG besar/baru (mis. AutoCAD 2018, 50+ MB).
# Bila gagal, pakai scripts/convert_local.py (ODA File Converter) di laptop, lalu unggah DXF-nya.
set -u
have() { command -v dwg2dxf >/dev/null 2>&1 || [ -n "${DWG2DXF_BIN:-}" ] && [ -x "${DWG2DXF_BIN:-/nonexistent}" ]; }
if have; then echo "OK: dwg2dxf sudah tersedia: $(command -v dwg2dxf || echo "$DWG2DXF_BIN")"; exit 0; fi
SUDO=""; [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1 && SUDO="sudo"
if command -v apt-get >/dev/null 2>&1; then
  echo "Mencoba: apt-get install libredwg-utils ..."
  $SUDO apt-get update -qq >/dev/null 2>&1
  $SUDO apt-get install -y -qq libredwg-utils >/dev/null 2>&1 || echo "apt-get gagal (tidak ada izin/jaringan/paket)."
fi
if command -v dwg2dxf >/dev/null 2>&1; then
  dwg2dxf --version 2>&1 | head -1
  echo "OK: dwg2dxf terpasang. Ini belum menjamin DWG besar terbaca; hasil konversi tetap diverifikasi oleh cad.py."
  exit 0
fi
echo "GAGAL: dwg2dxf tidak tersedia. Alternatif: jalankan scripts/convert_local.py (ODA File Converter) di laptop, atau ekspor SAVEAS DXF 2013/2018 / PLOT PDF vektor dari AutoCAD." >&2
exit 1
