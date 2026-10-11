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
REM Single stable filename (not the hash-named frontend assets) so Drive
REM sync treats every run as an update to the same file, not a new upload.
copy /y "%APK_SRC%" "%DRIVE_DIR%\BudgetTracker-debug.apk" >nul
if errorlevel 1 (
    echo.
    echo ERROR: Failed to copy the APK into %DRIVE_DIR%.
    pause
    exit /b 1
)
echo Done - %DRIVE_DIR%\BudgetTracker-debug.apk

echo.
echo ============================================
echo  Sync complete - APK built and copied to Google Drive
echo ============================================
echo.
pause
endlocal
