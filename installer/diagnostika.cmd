@echo off
chcp 65001 > nul
echo ==============================================
echo  SteamPACC: проверка программы
echo ==============================================
echo.
"%~dp0SteamPACC.exe" --selftest
echo.
echo Отчёт сохранён: %APPDATA%\SteamPACC\samoproverka.txt
echo Журнал работы: %APPDATA%\SteamPACC\steampacc.log
echo.
start "" notepad "%APPDATA%\SteamPACC\samoproverka.txt"
pause
