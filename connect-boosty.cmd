@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Не найдено локальное окружение .venv. Смотрите docs\boosty-production.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\connect_boosty.py %*
set "boosty_exit=%errorlevel%"
pause
exit /b %boosty_exit%
