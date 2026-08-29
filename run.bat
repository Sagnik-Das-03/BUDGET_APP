@echo off

REM Double-clicking a .bat makes Explorer launch it as "cmd.exe /c <path>" - a throwaway
REM console that Windows tears down the instant the script's last line runs, no matter how
REM many "pause" statements are inside it (the window itself is closed by the parent, not
REM by this script). Typing "run.bat" at an already-open cmd/PowerShell prompt does NOT
REM have "/c" in its command line, so this only fires for the double-click case - it
REM relaunches into a "cmd /k" window, which Windows leaves open after the script ends
REM or crashes, until you close it or type "exit" yourself.
echo %cmdcmdline% | find /i "/c" >nul
if not errorlevel 1 (
    start "Budget Tracker" cmd /k "%~f0"
    exit /b
)

setlocal
cd /d "%~dp0"

echo ============================================
echo  Budget Tracker launcher
echo ============================================
echo.

echo [1/6] Checking for Python 3.13...
py -3.13 --version
if errorlevel 1 (
    echo.
    echo ERROR: Python 3.13 not found via "py -3.13". Install it from python.org, then re-run this script.
    pause
    exit /b 1
)

echo.
echo [2/6] Checking for Node.js / npm...
call npm --version
if errorlevel 1 (
    echo.
    echo ERROR: npm not found. Install Node.js from nodejs.org, then re-run this script.
    pause
    exit /b 1
)

echo.
echo [3/6] Installing frontend dependencies...
cd frontend
call npm install
if errorlevel 1 (
    echo.
    echo ERROR: Frontend dependency install failed. See output above.
    cd ..
    pause
    exit /b 1
)

echo.
echo [4/6] Building frontend...
call npm run build
if errorlevel 1 (
    echo.
    echo ERROR: Frontend build failed. See output above.
    cd ..
    pause
    exit /b 1
)
cd ..

echo.
echo [5/6] Setting up backend virtual environment...
cd backend

if exist ".venv" (
    echo Removing leftover virtual environment from a previous run...
    rmdir /s /q ".venv" 2>nul
)

echo Creating virtual environment (Python 3.13)...
py -3.13 -m venv .venv
if errorlevel 1 (
    echo.
    echo ERROR: Failed to create the virtual environment.
    cd ..
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

echo Upgrading pip...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo.
    echo ERROR: Failed to upgrade pip.
    call ".venv\Scripts\deactivate.bat" 2>nul
    cd ..
    pause
    exit /b 1
)

echo Installing backend dependencies (this can take a minute)...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: Failed to install backend dependencies. See output above.
    call ".venv\Scripts\deactivate.bat" 2>nul
    cd ..
    pause
    exit /b 1
)

if not exist ".env" (
    echo Creating .env from .env.example - edit it to add your Google credentials later.
    copy .env.example .env >nul
)

if not exist "data" mkdir data

echo.
echo [6/6] Starting Budget Tracker...
echo   URL: http://127.0.0.1:8000
echo   Press Ctrl+C in this window to stop the server.
echo   (The backend virtual environment is deleted automatically on shutdown to save
echo    disk space - frontend/node_modules and frontend/dist are kept, since npm
echo    installs are slow - only pip/venv gets the fresh-each-launch treatment.)
echo.
start "" http://127.0.0.1:8000
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
if errorlevel 1 (
    echo.
    echo ERROR: The backend server exited with an error. See output above.
)

call ".venv\Scripts\deactivate.bat" 2>nul
echo.
echo Cleaning up backend virtual environment...
rmdir /s /q ".venv" 2>nul

cd ..

echo.
echo ============================================
echo  Budget Tracker has stopped.
echo ============================================
pause
endlocal
