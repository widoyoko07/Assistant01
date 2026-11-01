#!/usr/bin/env bash
# Hentikan bot (dan pengulangnya). Aman dijalankan walau bot tidak aktif.
pkill -f "scripts/start_bot.sh" 2>/dev/null
pkill -f "automation_hub.pribadi.bot" 2>/dev/null
echo "bot dihentikan"
