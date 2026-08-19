@echo off
title JET Otomasyon Araci v4.0

echo ==============================================
echo      JET Otomasyon Araci v4.0 baslatiliyor
echo ==============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [HATA] Python bulunamadi. https://www.python.org/downloads/
    pause
    exit /b 1
)

if not exist "venv" (
    echo [*] Sanal ortam olusturuluyor...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo [*] Bagimliliklar kuruluyor...
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt

echo.
echo [OK] Baslatiliyor: http://127.0.0.1:5757
echo.

python src\app.py
pause
