@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title DeRo Cinematic Visualizer v0.1.17 - Fullscreen Preview

rem Find FFmpeg without requiring any Windows PATH changes.
set "FFMPEG_DIR="
if exist "C:\FFmpeg\bin\ffmpeg.exe" set "FFMPEG_DIR=C:\FFmpeg\bin"
if not defined FFMPEG_DIR if exist "%~dp0tools\ffmpeg\bin\ffmpeg.exe" set "FFMPEG_DIR=%~dp0tools\ffmpeg\bin"
if not defined FFMPEG_DIR if exist "%~dp0tools\ffmpeg.exe" set "FFMPEG_DIR=%~dp0tools"
if not defined FFMPEG_DIR if exist "%~dp0ffmpeg.exe" set "FFMPEG_DIR=%~dp0"
if not defined FFMPEG_DIR (
  where ffmpeg.exe >nul 2>&1
  if not errorlevel 1 for /f "delims=" %%F in ('where ffmpeg.exe 2^>nul') do if not defined FFMPEG_DIR set "FFMPEG_DIR=%%~dpF"
)
if not defined FFMPEG_DIR (
  echo ERROR: FFmpeg was not found in C:\FFmpeg\bin, the app folder, or PATH.
  pause
  exit /b 1
)
set "PATH=%FFMPEG_DIR%;%PATH%"
echo Using FFmpeg from: "%FFMPEG_DIR%"

if not exist "visualizer_app.py" (
  echo ERROR: visualizer_app.py was not found beside this launcher.
  echo Extract the full ZIP before running this BAT file.
  pause
  exit /b 1
)

py -3.12 --version >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python 3.12 was not found via the Windows py launcher.
  pause
  exit /b 1
)

py -3.12 -c "import numpy, PIL, sounddevice" >nul 2>&1
if errorlevel 1 (
  echo Installing Python 3.12 dependencies...
  py -3.12 -m pip install -r requirements.txt
  if errorlevel 1 (
    echo ERROR: Python package installation failed.
    pause
    exit /b 1
  )
)

echo Starting DeRo Cinematic Visualizer...
py -3.12 visualizer_app.py
if errorlevel 1 (
  echo ERROR: DeRo Cinematic Visualizer exited with an error.
  pause
)
endlocal
