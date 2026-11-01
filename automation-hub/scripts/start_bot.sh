#!/usr/bin/env bash
# Jalankan bot keuangan dan nyalakan ulang bila crash. Berhenti bila bot lain sudah jalan (kode 3)
# atau bot dihentikan normal (kode 0). Log: data/logs/bot_service.log
cd "$(dirname "$0")/.." || exit 1
mkdir -p data/logs
PY="$(cd .. && pwd)/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3 || command -v python)"
while true; do
  "$PY" -m automation_hub.pribadi.bot >> data/logs/bot_service.log 2>&1
  rc=$?
  if [ "$rc" -eq 0 ] || [ "$rc" -eq 3 ]; then exit 0; fi
  echo "$(date '+%F %T') bot berhenti (kode $rc), mulai ulang 15 detik lagi" >> data/logs/bot_service.log
  sleep 15
done
