#!/usr/bin/env bash
# Perintah singkat Daily MP.  Pakai:
#   run_daily_mp.sh                      -> tanggal terakhir yang ada datanya
#   run_daily_mp.sh 2026-09-29           -> satu hari (rekap + cross-check + Excel)
#   run_daily_mp.sh 2026-09-26 2026-09-29 -> rentang (ringkasan + Excel per hari)
# Posting di /tmp/mp, Attendance .txt di /tmp/mp_att (ubah lewat DIR / ATT).
DIR="${DIR:-/tmp/mp}"; ATT="${ATT:-/tmp/mp_att}"; H="$(cd "$(dirname "$0")" && pwd)"
if [ "$#" -ge 2 ]; then python3 "$H/dailymp.py" --dir "$DIR" --range "$1" "$2" --xlsx
else python3 "$H/dailymp.py" --dir "$DIR" ${1:+--date "$1"} --xc --att-dir "$ATT" --xlsx; fi
