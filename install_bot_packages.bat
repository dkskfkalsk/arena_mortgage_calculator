@echo off
echo ======================================
echo   Installing Bot Packages
echo ======================================
echo.

cd /d "%~dp0"

echo [1/2] Activating virtual environment...
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo [OK] Virtual environment activated
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    echo [OK] Virtual environment activated
) else (
    echo [WARN] No virtual environment found, using system Python
)

echo.
echo [2/2] Installing required packages...
echo.

pip install python-telegram-bot python-dotenv

echo.
echo ======================================
echo [OK] Installation complete!
echo Now run start_pdf_bot.bat
echo ======================================
echo.

pause
