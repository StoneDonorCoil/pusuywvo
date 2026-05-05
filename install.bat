@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

:: ═══════════════════════════════════════════════════════════
:: Auto Clicker — Installer
:: ═══════════════════════════════════════════════════════════

title Auto Clicker — Setup

:: Enable ANSI colors
for /f "tokens=3" %%a in ('reg query "HKCU\Console" /v VirtualTerminalLevel 2^>nul') do set "VT=%%a"
reg add "HKCU\Console" /v VirtualTerminalLevel /t REG_DWORD /d 1 /f >nul 2>&1

set "ESC="
set "R=%ESC%[91m"
set "G=%ESC%[92m"
set "Y=%ESC%[93m"
set "B=%ESC%[94m"
set "M=%ESC%[95m"
set "C=%ESC%[96m"
set "W=%ESC%[97m"
set "DIM=%ESC%[90m"
set "BOLD=%ESC%[1m"
set "RST=%ESC%[0m"
set "CLR=%ESC%[2J%ESC%[H"

:: ── Intro Animation ─────────────────────────────────────────
cls
echo.
echo.
call :animLine "%B%    ╔══════════════════════════════════════════╗%RST%"
call :animLine "%B%    ║%RST%%BOLD%%W%         AUTO CLICKER — SETUP            %RST%%B%║%RST%"
call :animLine "%B%    ╚══════════════════════════════════════════╝%RST%"
echo.
call :animLine "%DIM%    Preparing installation...%RST%"
echo.
ping -n 2 127.0.0.1 >nul

:: ── Step 1: Check Python ────────────────────────────────────
call :header "CHECKING PYTHON"

python --version >nul 2>&1
if %errorlevel% neq 0 (
    call :status "!" "Y" "Python not found"
    echo.
    call :status ">" "C" "Downloading Python installer..."
    echo.

    call :progressBar 30 "Downloading Python 3.12"

    powershell -Command "& { $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe' -OutFile '%TEMP%\python_installer.exe' }" 2>nul

    call :status ">" "C" "Installing Python..."
    echo.
    call :progressBar 45 "Installing Python 3.12"

    start /wait "" "%TEMP%\python_installer.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1
    if %errorlevel% neq 0 (
        call :status "X" "R" "Python install failed. Please install manually:"
        echo     %C%https://www.python.org/downloads/%RST%
        echo.
        pause
        exit /b 1
    )

    :: Refresh PATH
    set "PATH=%LocalAppData%\Programs\Python\Python312;%LocalAppData%\Programs\Python\Python312\Scripts;%PATH%"
    set "PATH=C:\Python312;C:\Python312\Scripts;%PATH%"

    call :status "+" "G" "Python installed successfully"
) else (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
    call :status "+" "G" "Python !PYVER! found"
)
echo.

:: ── Step 2: Upgrade pip ─────────────────────────────────────
call :header "UPGRADING PIP"
call :spinner 8 "Updating pip"
python -m pip install --upgrade pip --quiet 2>nul
call :status "+" "G" "pip is up to date"
echo.

:: ── Step 3: Install PySide6 ─────────────────────────────────
call :header "INSTALLING DEPENDENCIES"
echo.

set "TOTAL=2"
set "DONE=0"

:: PySide6
call :status ">" "C" "Installing PySide6 (Qt framework)..."
echo.
call :progressBar 60 "PySide6"
python -m pip install PySide6 --quiet 2>nul
if %errorlevel% neq 0 (
    call :status "X" "R" "Failed to install PySide6"
    pause
    exit /b 1
)
set /a DONE+=1
call :status "+" "G" "PySide6 installed  [!DONE!/!TOTAL!]"
echo.

:: pynput
call :status ">" "C" "Installing pynput (input listener)..."
echo.
call :progressBar 25 "pynput"
python -m pip install pynput --quiet 2>nul
if %errorlevel% neq 0 (
    call :status "X" "R" "Failed to install pynput"
    pause
    exit /b 1
)
set /a DONE+=1
call :status "+" "G" "pynput installed   [!DONE!/!TOTAL!]"
echo.

:: ── Step 4: Verify ──────────────────────────────────────────
call :header "VERIFYING INSTALLATION"
call :spinner 6 "Running checks"

python -c "import PySide6; import pynput" 2>nul
if %errorlevel% neq 0 (
    call :status "X" "R" "Verification failed — some modules missing"
    pause
    exit /b 1
)
call :status "+" "G" "All modules verified"
echo.

:: ── Done ────────────────────────────────────────────────────
echo.
echo  %B%    ╔══════════════════════════════════════════╗%RST%
echo  %B%    ║%RST%%BOLD%%G%        INSTALLATION COMPLETE              %RST%%B%║%RST%
echo  %B%    ╚══════════════════════════════════════════╝%RST%
echo.
call :animLine "%W%    Starting Auto Clicker...%RST%"
echo.
ping -n 3 127.0.0.1 >nul

:: Launch
cd /d "%~dp0"
start "" python run.py
exit /b 0

:: ═══════════════════════════════════════════════════════════
:: FUNCTIONS
:: ═══════════════════════════════════════════════════════════

:header
echo     %M%━━━━ %BOLD%%W%%~1%RST% %M%━━━━%RST%
echo.
goto :eof

:status
:: %1=symbol %2=color_letter %3=message
set "SYM=%~1"
set "COL=!%~2!"
echo     !COL![!SYM!]%RST% %W%%~3%RST%
goto :eof

:animLine
set "LINE=%~1"
set "LEN=0"
:: Just echo with slight delay for effect
echo %~1
ping -n 1 127.0.0.1 >nul
goto :eof

:progressBar
:: %1=steps %2=label
set "STEPS=%~1"
set "LABEL=%~2"
set "BAR_W=32"

for /l %%i in (1,1,%STEPS%) do (
    set /a "PCT=%%i * 100 / %STEPS%"
    set /a "FILLED=%%i * %BAR_W% / %STEPS%"
    set /a "EMPTY=%BAR_W% - !FILLED!"

    set "FILL="
    for /l %%f in (1,1,!FILLED!) do set "FILL=!FILL!█"
    set "EMPT="
    if !EMPTY! gtr 0 (
        for /l %%e in (1,1,!EMPTY!) do set "EMPT=!EMPT!░"
    )

    <nul set /p "=%ESC%[2K%ESC%[G     %C%!LABEL!%RST% %DIM%[%RST%%B%!FILL!%DIM%!EMPT!%RST%%DIM%]%RST% %W%!PCT!%%%RST%"
    ping -n 1 127.0.0.1 >nul 2>&1
)
echo.
goto :eof

:spinner
:: %1=iterations %2=label
set "SP_CHARS=⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏"
set "SP_I=0"
for /l %%i in (1,1,%~1) do (
    set /a "SP_I=%%i %% 10"
    set "SP_C=⠋"
    if !SP_I!==1 set "SP_C=⠙"
    if !SP_I!==2 set "SP_C=⠹"
    if !SP_I!==3 set "SP_C=⠸"
    if !SP_I!==4 set "SP_C=⠼"
    if !SP_I!==5 set "SP_C=⠴"
    if !SP_I!==6 set "SP_C=⠦"
    if !SP_I!==7 set "SP_C=⠧"
    if !SP_I!==8 set "SP_C=⠇"
    if !SP_I!==9 set "SP_C=⠏"
    <nul set /p "=%ESC%[2K%ESC%[G     %C%!SP_C!%RST% %W%%~2%RST%%DIM%...%RST%"
    ping -n 1 127.0.0.1 >nul 2>&1
)
echo.
goto :eof
