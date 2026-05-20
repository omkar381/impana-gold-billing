@echo off
title Impana Gold Billing System
cd /d "%~dp0"

echo ==================================================
echo         IMPANA GOLD BILLING SYSTEM
echo ==================================================
echo.

set FLASK_ENV=production
set FLASK_APP=app
set DATABASE_URL=postgresql://neondb_owner:npg_2CZtvbkl1gFO@ep-damp-sun-aobcdfmv.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require

:: Check if virtual environment exists
if exist "venv\Scripts\python.exe" (
    echo [OK] Found Virtual Environment.
    set PYTHON_CMD=venv\Scripts\python.exe
    set PIP_CMD=venv\Scripts\pip.exe
) else (
    echo [!] No venv found. Using system Python.
    set PYTHON_CMD=python
    set PIP_CMD=pip
)

:: Auto-install missing dependencies
echo [->] Checking dependencies...
%PIP_CMD% install -q flask flask-sqlalchemy flask-login flask-wtf psycopg2-binary python-dotenv 2>nul

:: Start Flask silently in a separate minimized window
echo [->] Starting Server Engine...
start "Impana Gold Server" /MIN %PYTHON_CMD% -m flask --app app run --host 127.0.0.1 --port 5000 --no-debugger

:: Wait 4 seconds for server to boot up
timeout /t 4 /nobreak >nul

:: Open default browser
echo [->] Opening Web Browser...
start "" "http://127.0.0.1:5000"

echo.
echo ==================================================
echo  APP IS RUNNING. Minimise this window. 
echo  DO NOT CLOSE THE MINIMISED SERVER WINDOW.
echo ==================================================
timeout /t 5 >nul
exit
