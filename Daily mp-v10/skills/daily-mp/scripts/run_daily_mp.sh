#!/usr/bin/env bash
# Perintah singkat Daily MP.  Pakai:
#   run_daily_mp.sh [tanggal]                 -> tampil ringkas (belum ada Excel)
#   run_daily_mp.sh --excel [tanggal]         -> sama + Excel (jalankan setelah user setuju)
#   run_daily_mp.sh [--excel] dari sampai     -> rentang, ringkasan + (Excel per hari)
# Posting di /tmp/mp, Attendance .txt (hasil pdf_to_att.py) di /tmp/mp_att (ubah lewat DIR / ATT).
DIR="${DIR:-/tmp/mp}"; ATT="${ATT:-/tmp/mp_att}"; H="$(cd "$(dirname "$0")" && pwd)"; X=""
[ "$1" = "--excel" ] && { X="--xlsx"; shift; }
if [ "$#" -ge 2 ]; then python3 "$H/dailymp.py" --dir "$DIR" --att-dir "$ATT" --range "$1" "$2" $X
else python3 "$H/dailymp.py" --dir "$DIR" --att-dir "$ATT" ${1:+--date "$1"} --xc --compact $X; fi
