@echo off

REM Same double-click-vs-typed-in-a-terminal handling as run.bat - see the
REM comment there for why this is needed at all.
echo %cmdcmdline% | find /i "/c" >nul
if not errorlevel 1 (
    start "Sync Android App" cmd /k "%~f0"
    exit /b
)

setlocal
cd /d "%~dp0"

echo ============================================
echo  Budget Tracker (Android) - sync frontend + backend
echo ============================================
echo.
echo There is only ONE frontend and ONE backend - this builds the frontend
echo and copies both it and backend\app\ into the Android app, which hosts
echo the real app read-only (see android\app\src\main\python\server.py).
echo Build the APK yourself from Android Studio afterwards.
echo.

echo [1/3] Building frontend...
cd frontend
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
echo [2/3] Syncing frontend\dist into the Android app...
robocopy frontend\dist android\app\src\main\python\static /MIR /NFL /NDL /NJH >nul
if errorlevel 8 (
    echo.
    echo ERROR: Failed to copy frontend\dist into the Android app.
    pause
    exit /b 1
)
echo Done.

echo.
echo [3/3] Syncing backend\app into the Android app...
robocopy backend\app android\app\src\main\python\app /MIR /XF cli.py /XD __pycache__ /NFL /NDL /NJH >nul
if errorlevel 8 (
    echo.
    echo ERROR: Failed to copy backend\app into the Android app.
    pause
    exit /b 1
)
echo Done.

if not exist "android\app\src\main\python\dashboard_credentials.json" (
    echo.
    echo WARNING: android\app\src\main\python\dashboard_credentials.json is missing -
    echo the app will build fine but every dashboard request will fail with a 503
    echo until you drop your read-only service account key there. See
    echo "Viewing your dashboard from your phone" in README.md.
)

echo.
echo ============================================
echo  Sync complete - build the APK from Android Studio
echo ============================================
echo.
pause
endlocal
