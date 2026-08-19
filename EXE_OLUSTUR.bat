@echo off
chcp 65001 >nul
title JET — EXE Oluşturma

echo ╔══════════════════════════════════════════════════════╗
echo ║     JET Otomasyon Aracı — EXE Oluşturucu           ║
echo ╚══════════════════════════════════════════════════════╝
echo.
echo Bu script tek dosya .exe oluşturur (dist\JET_Otomasyon.exe)
echo.

call venv\Scripts\activate.bat 2>nul
if errorlevel 1 (
    echo [*] Sanal ortam bulunamadı, önce CALISTIR.bat çalıştırın.
    pause
    exit /b 1
)

pip install -q pyinstaller

echo [*] EXE oluşturuluyor...
pyinstaller JET.spec --clean --noconfirm

if exist "dist\JET_Otomasyon.exe" (
    echo.
    echo ╔══════════════════════════════════════════════════════╗
    echo ║   BAŞARILI! EXE oluşturuldu:                        ║
    echo ║   dist\JET_Otomasyon.exe                            ║
    echo ╚══════════════════════════════════════════════════════╝
    echo.
    echo EXE'yi istediğiniz yere kopyalayabilirsiniz.
    echo Python veya internet bağlantısı gerekmez.
) else (
    echo [HATA] EXE oluşturulamadı. Yukarıdaki hata mesajlarını inceleyin.
)

pause
