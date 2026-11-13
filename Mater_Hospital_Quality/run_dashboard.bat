@echo off
rem Starts the Mater Hospital quality dashboard. Leave this window open while you use it;
rem closing it stops the dashboard. Everything printed is also saved to dashboard_log.txt.
cd /d "%~dp0"
set PYTHONUNBUFFERED=1

rem Use this folder's own environment; if setup has not been run yet, borrow the one
rem from C:\Users\jason\stroke_quality_dashboard (it has the same packages).
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%USERPROFILE%\stroke_quality_dashboard\.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo No Python environment found. Double-click setup.bat first.
    pause
    exit /b 1
)

echo Starting the Mater Hospital dashboard...
echo Your browser will open at http://localhost:8501 when it is ready.
echo Using %PY%
powershell -NoProfile -ExecutionPolicy Bypass -Command "& $env:PY -m streamlit run app.py --server.address localhost --server.port 8501 --server.headless false 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object -FilePath dashboard_log.txt"
echo.
echo The dashboard has stopped.
pause
