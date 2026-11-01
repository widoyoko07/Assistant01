# K4: bot jalan otomatis saat login

Bot (WSL Ubuntu) dijalankan oleh `scripts/start_bot.sh`: menyalakan ulang bila crash, berhenti bila bot lain sudah jalan.
Windows memanggilnya lewat `KeuanganBot.vbs` di folder Startup (tersembunyi, tanpa jendela, saat login). Tugas terjadwal tidak dipakai karena butuh Administrator.

## Pasang (sekali)
1. Hentikan bot manual: Ctrl+C di terminalnya.
2. Di PowerShell biasa:
   `powershell -ExecutionPolicy Bypass -File "\\wsl$\Ubuntu\home\dhaniwidoyoko\Assistant01\automation-hub\scripts\install_autostart.ps1"`
3. Mulai tanpa logout: `wscript.exe "%USERPROFILE%\AutomationHub\start_bot_hidden.vbs"`
4. Cek: kirim pesan ke bot, atau lihat `data/logs/bot_service.log` dan `data/logs/pribadi_bot_<tanggal>.log`.

## Kelola
- Hentikan: `wsl -d Ubuntu --exec bash -lc "~/Assistant01/automation-hub/scripts/stop_bot.sh"`
- Hapus autostart: hapus `KeuanganBot.vbs` dari folder Startup (Win+R, ketik `shell:startup`)
- Hanya satu bot boleh polling. Bot kedua keluar sendiri (kode 3) sehingga tidak bentrok di Telegram.

## Batas
- Hanya jalan saat laptop menyala dan Anda sudah login ke Windows. Pesan saat laptop mati ditunda Telegram (maks. 24 jam).
