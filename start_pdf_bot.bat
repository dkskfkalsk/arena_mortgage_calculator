@echo off
echo ======================================
echo   PDF Bot Starting...
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
echo [2/2] Starting bot...
echo ======================================
echo Bot is running!
echo Send PDF files to the bot.
echo Press Ctrl+C to stop.
echo ======================================
echo.

python local_pdf_bot.py

if errorlevel 1 (
    echo.
    echo [ERROR] Bot failed to start!
    echo Please install required packages:
    echo.
    echo pip install python-telegram-bot python-dotenv
    echo.
    pause
)
