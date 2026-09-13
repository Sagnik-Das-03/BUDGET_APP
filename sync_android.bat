@echo off

REM Same double-click-vs-typed-in-a-terminal handling as run.bat - see the
REM comment there for why this is needed at all.
echo %cmdcmdline% | find /i "/c" >nul
if not errorlevel 1 (
    start "Sync Android Dashboard" cmd /k "%~f0"
    exit /b
)

setlocal
cd /d "%~dp0"

echo ============================================
echo  Budget Dashboard (Android) - sync frontend
echo ============================================
echo.
echo There is only ONE frontend build - this builds it and copies the same
echo output into the Android app's two static/ folders. Build the APK
echo yourself from Android Studio afterwards. See "Viewing your dashboard
echo from your phone" in README.md for the full picture (useCapabilities()
echo is what makes one build work for both apps).
echo.

echo [1/2] Building frontend...
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
echo [2/2] Syncing frontend\dist into the Android app...
robocopy frontend\dist android_dashboard\static /MIR /NFL /NDL /NJH >nul
if errorlevel 8 (
    echo.
    echo ERROR: Failed to copy frontend\dist into android_dashboard\static.
    pause
    exit /b 1
)
robocopy frontend\dist android\app\src\main\python\static /MIR /NFL /NDL /NJH >nul
if errorlevel 8 (
    echo.
    echo ERROR: Failed to copy frontend\dist into android\app\src\main\python\static.
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
