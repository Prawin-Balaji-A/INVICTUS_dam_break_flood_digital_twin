@echo off
REM ============================================================
REM  Mettur Dam - Failure ^& Flood Simulator (Three.js / WebGL)
REM  Double-click to launch the local dev server.
REM ============================================================
setlocal

REM Run from this script's own folder, wherever it was launched from.
cd /d "%~dp0"

REM Make sure Node.js is available.
where node >nul 2>nul
if errorlevel 1 (
  echo.
  echo [ERROR] Node.js was not found on your PATH.
  echo         Install it from https://nodejs.org/ ^(LTS^) and re-run this file.
  echo.
  pause
  exit /b 1
)

REM Install dependencies the first time ^(no node_modules folder yet^).
if not exist "node_modules" (
  echo.
  echo [setup] Installing dependencies - this only happens the first time...
  echo.
  call npm install
  if errorlevel 1 (
    echo.
    echo [ERROR] npm install failed. Scroll up for details.
    echo.
    pause
    exit /b 1
  )
)

echo.
echo [run] Starting the Mettur Dam simulator on http://localhost:3000
echo       A browser tab will open automatically. Press Ctrl+C here to stop.
echo.
call npm run dev

REM Keep the window open if the server exits or crashes.
pause
endlocal
