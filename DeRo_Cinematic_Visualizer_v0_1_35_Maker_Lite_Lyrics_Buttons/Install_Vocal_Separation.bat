@echo off
setlocal
cd /d "%~dp0"
py -3.12 "install_vocal_separation.py"
if errorlevel 1 echo Separation setup did not complete. Keep your existing working CUDA environment.
pause
