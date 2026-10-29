@echo off
cd /d "%~dp0"
py -3.12 install_vocal_separation.py --alignment
pause
