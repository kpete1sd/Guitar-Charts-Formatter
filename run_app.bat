@echo off
REM Double-click to start the Gig Chart Formatter on Windows.
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python was not found. Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" on the first install screen.
  echo.
  pause
  exit /b 1
)

if not exist .venv\Scripts\activate.bat (
  echo First run: setting up the app. This takes a few minutes...
  python -m venv .venv
  call .venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate.bat
)

python -m streamlit run app.py
pause
