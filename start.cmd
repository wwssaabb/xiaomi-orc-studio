@echo off
setlocal
cd /d "%~dp0"
title Xiaomi-OCR Studio

rem Prefer the project venv (has all engine deps), then validate any other
rem python on PATH - WindowsApps stubs and broken installs are rejected.
set "PY="
if exist "Xiaomi-OCR-0\skills\xiaomi-ocr\.venv\Scripts\python.exe" set "PY=Xiaomi-OCR-0\skills\xiaomi-ocr\.venv\Scripts\python.exe"
if not defined PY if exist "..\Xiaomi-OCR-0\skills\xiaomi-ocr\.venv\Scripts\python.exe" set "PY=..\Xiaomi-OCR-0\skills\xiaomi-ocr\.venv\Scripts\python.exe"

if not defined PY (
  for %%C in (python py) do (
    if not defined PY (
      %%C --version >nul 2>nul && set "PY=%%C"
    )
  )
)

if not defined PY (
  echo [x] 找不到可用的 Python 3.10+。
  echo     请安装 Python 或把 Xiaomi-OCR-0 仓库放在本项目同级目录。
  pause
  exit /b 1
)

"%PY%" --version >nul 2>nul
if errorlevel 1 (
  echo [x] Python 解释器无法运行: %PY%
  pause
  exit /b 1
)
echo [*] Python: %PY%

if not exist "node_modules" (
  echo [*] 首次运行，安装前端依赖...
  call npm install --no-audit --no-fund
  if errorlevel 1 ( echo [x] 依赖安装失败。 & pause & exit /b 1 )
)

if not exist "dist\index.html" (
  echo [*] 构建前端...
  call npm run build
  if errorlevel 1 ( echo [x] 构建失败。 & pause & exit /b 1 )
)

echo [*] 启动本地网关: http://127.0.0.1:8787
start "" http://127.0.0.1:8787
"%PY%" server\app.py
if errorlevel 1 (
  echo.
  echo [x] 网关启动失败，请检查上方错误信息。
  pause
  exit /b 1
)
pause
