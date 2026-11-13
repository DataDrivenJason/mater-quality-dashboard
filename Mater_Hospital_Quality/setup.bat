@echo off
rem One-off setup: creates this folder's own Python environment (.venv) and installs
rem the packages in requirements.txt. Needs internet access to pypi.org. Takes a few minutes.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    echo .venv already exists. To rebuild it, delete the .venv folder and run this again.
    goto install
)
echo Creating the Python environment...
py -3 -m venv .venv 2>nul || python -m venv .venv
if not exist ".venv\Scripts\python.exe" (
    echo Could not create .venv. Is Python installed? Try:  py --version
    pause
    exit /b 1
)
:install
echo Installing packages...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Package installation failed. Copy the messages above into the chat.
    pause
    exit /b 1
)
echo.
echo Setup complete. Double-click run_dashboard.bat to start the dashboard.
pause
