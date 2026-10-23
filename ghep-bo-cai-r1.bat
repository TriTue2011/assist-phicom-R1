@echo off
title Ghep Bo Cai R1.exe
cd /d "%~dp0"
if not exist "Bo Cai R1.exe.00" goto thieu
if not exist "Bo Cai R1.exe.01" goto thieu
echo Dang ghep 2 phan thanh Bo Cai R1.exe ...
copy /b "Bo Cai R1.exe.00"+"Bo Cai R1.exe.01" "Bo Cai R1.exe" >nul
if errorlevel 1 goto loi
echo Da ghep xong!
echo.
echo Ma SHA-256 cua file vua ghep (phai khop voi dong duoi):
certutil -hashfile "Bo Cai R1.exe" SHA256
echo 4aa62e51426b98bcda091ce8711ad1b191b150629551f02f2e6f7c3e998ea2a5
echo.
pause
exit /b 0
:thieu
echo THIEU FILE: can co ca "Bo Cai R1.exe.00" va "Bo Cai R1.exe.01" nam cung thu muc voi file .bat nay.
pause
exit /b 1
:loi
echo Ghep that bai, kiem tra lai 2 file phan.
pause
exit /b 1
