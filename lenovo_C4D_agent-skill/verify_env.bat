@echo off
"%SystemRoot%\System32\chcp.com" 65001 >nul
"%SystemRoot%\System32\mode.com" con: cols=130 lines=42
cd /d "%~dp0"
python verify_env.py
echo.
echo ==== window kept open for screenshot - press any key to close ====
pause >nul
