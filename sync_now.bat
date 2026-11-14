@echo off

REM Same double-click-vs-typed-in-a-terminal handling as run.bat - see the
REM comment there for why this is needed at all.
echo %cmdcmdline% | find /i "/c" >nul
if not errorlevel 1 (
    start "Budget Tracker Sync" cmd /k "%~f0"
    exit /b
)

setlocal
cd /d "%~dp0"

echo ============================================
echo  Budget Tracker - sync now
echo ============================================
echo.
echo Runs one full sync cycle for whichever profile is currently active on
echo this machine (same pull-then-push-then-reports cycle as the app's own
echo background sync / "Sync Now" button) without opening the app itself.
echo.

cd backend
if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: backend\.venv isn't set up yet - run run.bat at least once first.
    cd ..
    pause
    exit /b 1
)
call ".venv\Scripts\activate.bat"

python -m app.cli sync-now
set SYNC_RESULT=%errorlevel%

call ".venv\Scripts\deactivate.bat" 2>nul
cd ..

echo.
if not "%SYNC_RESULT%"=="0" (
    echo ERROR: Sync command exited with an error. See output above.
) else (
    echo ============================================
    echo  Sync complete
    echo ============================================
)
echo.
pause
endlocal
