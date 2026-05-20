@echo off
title Impana Gold — Starting...
cd /d "%~dp0"
set FLASK_ENV=production
set FLASK_APP=app

echo Starting Impana Gold Billing System...
echo Please wait, opening in your browser...

start "" "venv\Scripts\pythonw.exe" -m flask --app app run --host 127.0.0.1 --port 5000 --no-debugger

timeout /t 3 /nobreak >nul

start "" "http://127.0.0.1:5000"

exit
