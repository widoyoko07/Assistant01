@echo off
rem Seret folder (atau file .dwg) ke file ini, atau: convert_local.bat "C:\gambar\RFS-020026"
rem Butuh Python dan ODA File Converter terpasang.
if "%~1"=="" (echo Pakai: convert_local.bat "folder-atau-file.dwg" & pause & exit /b 1)
python "%~dp0convert_local.py" "%~1"
pause
