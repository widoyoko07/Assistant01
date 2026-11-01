# Daftarkan bot keuangan agar jalan otomatis (tersembunyi) setiap Anda login ke Windows (lewat folder Startup).
# Jalankan SEKALI di PowerShell (tidak perlu Administrator):
#   powershell -ExecutionPolicy Bypass -File "\\wsl$\Ubuntu\home\<user>\Assistant01\automation-hub\scripts\install_autostart.ps1"
# Hapus: hapus file KeuanganBot.vbs dari folder Startup (Win+R -> shell:startup)
param(
    [string]$Distro = "Ubuntu",
    [string]$ScriptPath = ""   # kosong = otomatis dari lokasi skrip ini di WSL
)
$ErrorActionPreference = "Stop"
if (-not $ScriptPath) {
    $here = Split-Path -Parent $MyInvocation.MyCommand.Path          # \\wsl$\Ubuntu\home\...\scripts
    $ScriptPath = ($here -replace '^\\\\wsl(\.localhost|\$)\\[^\\]+', '') -replace '\\', '/'
    $ScriptPath = "$ScriptPath/start_bot.sh"
}
$dir = Join-Path $env:USERPROFILE "AutomationHub"
New-Item -ItemType Directory -Force $dir | Out-Null
$vbs = Join-Path $dir "start_bot_hidden.vbs"
$line = 'sh.Run "wsl.exe -d ' + $Distro + ' --exec bash -lc ""' + $ScriptPath + '""", 0, False'
Set-Content -Path $vbs -Encoding ASCII -Value @('Set sh = CreateObject("WScript.Shell")', $line)
# Folder Startup Windows: tidak butuh Administrator (tugas terjadwal "saat login" butuh).
$startup = [Environment]::GetFolderPath("Startup")
Copy-Item -Force $vbs (Join-Path $startup "KeuanganBot.vbs")
if (-not (Test-Path (Join-Path $startup "KeuanganBot.vbs"))) { throw "Gagal menaruh KeuanganBot.vbs di $startup" }
Write-Host "Terpasang: $startup\KeuanganBot.vbs  ->  $ScriptPath"
Write-Host "Jalan otomatis di login berikutnya. Mulai sekarang: wscript.exe `"$vbs`""
