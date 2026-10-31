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
echo Then it builds the debug APK itself and copies it into your Google
echo Drive folder, so it's one step from here to installing it on your phone.
echo.

echo [1/4] Building frontend...
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
echo [2/4] Syncing frontend\dist into the Android app...
robocopy frontend\dist android\app\src\main\python\static /MIR /NFL /NDL /NJH >nul
if errorlevel 8 (
    echo.
    echo ERROR: Failed to copy frontend\dist into the Android app.
    pause
    exit /b 1
)
echo Done.

echo.
echo [3/4] Syncing backend\app into the Android app...
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
echo [4/4] Building the debug APK and copying it to Google Drive...
cd android
call gradlew.bat assembleDebug
if errorlevel 1 (
    echo.
    echo ERROR: Gradle build failed. See output above.
    cd ..
    pause
    exit /b 1
)
cd ..

set APK_SRC=android\app\build\outputs\apk\debug\app-debug.apk
set DRIVE_DIR=G:\My Drive
if not exist "%APK_SRC%" (
    echo.
    echo ERROR: Build reported success but %APK_SRC% wasn't found.
    pause
    exit /b 1
)
if not exist "%DRIVE_DIR%" (
    echo.
    echo WARNING: %DRIVE_DIR% doesn't exist - is Google Drive for desktop running?
    echo The APK is still available locally at %APK_SRC%.
    pause
    exit /b 1
)
REM Each build gets its own timestamped filename (batch's %date%/%time% vary
REM by Windows locale and can't be trusted to parse the same way on every
REM machine, so PowerShell's Get-Date formats it instead) - lets you tell
REM builds apart in Drive, e.g. if you need to grab a specific one later.
for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmm"') do set BUILD_VERSION=%%T
set APK_NAME=BudgetTracker-debug-%BUILD_VERSION%.apk

copy /y "%APK_SRC%" "%DRIVE_DIR%\%APK_NAME%" >nul
if errorlevel 1 (
    echo.
    echo ERROR: Failed to copy the APK into %DRIVE_DIR%.
    pause
    exit /b 1
)
echo Done - %DRIVE_DIR%\%APK_NAME%

REM Only delete older builds AFTER the new one is confirmed in place, so a
REM failed upload never leaves you with zero APKs in Drive. Keeps exactly
REM one copy there at a time instead of accumulating one per sync run forever.
for %%F in ("%DRIVE_DIR%\BudgetTracker-debug-*.apk") do (
    if /i not "%%~nxF"=="%APK_NAME%" (
        del /f /q "%%F"
        echo Removed old build: %%~nxF
    )
)

echo.
echo ============================================
echo  Sync complete - APK built and copied to Google Drive
echo ============================================
echo.
pause
endlocal
