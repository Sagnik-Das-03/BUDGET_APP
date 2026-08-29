@echo off
setlocal
cd /d "%~dp0"

py -3.13 --version >nul 2>&1
if errorlevel 1 (
    echo Python 3.13 not found via "py -3.13". Install it from python.org, then re-run this script.
    pause
    exit /b 1
)

npm --version >nul 2>&1
if errorlevel 1 (
    echo npm not found. Install Node.js from nodejs.org, then re-run this script.
    pause
    exit /b 1
)

echo === Building frontend ===
cd frontend
call npm install
if errorlevel 1 (
    echo Frontend dependency install failed.
    pause
    exit /b 1
)
call npm run build
if errorlevel 1 (
    echo Frontend build failed.
    pause
    exit /b 1
)
cd ..

echo === Starting backend ===
cd backend

if exist ".venv" (
    echo Removing leftover virtual environment from a previous run...
    rmdir /s /q ".venv" 2>nul
)

echo Creating virtual environment (Python 3.13)...
py -3.13 -m venv .venv

call ".venv\Scripts\activate.bat"

echo Installing dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

if not exist ".env" (
    echo Creating .env from .env.example - edit it to add your Google credentials later.
    copy .env.example .env >nul
)

if not exist "data" mkdir data

echo Starting Budget Tracker at http://127.0.0.1:8000 ...
echo Press Ctrl+C to stop - the backend virtual environment is deleted automatically on
echo shutdown to save disk space (frontend/node_modules and frontend/dist are kept, since
echo npm installs are slow - only pip/venv gets the fresh-each-launch treatment).
start "" http://127.0.0.1:8000
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

call ".venv\Scripts\deactivate.bat" 2>nul
echo Cleaning up backend virtual environment...
rmdir /s /q ".venv" 2>nul

cd ..
endlocal
