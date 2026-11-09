@echo off
setlocal
cd /d "%~dp0"
title Xiaomi-OCR Studio

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY if exist "..\Xiaomi-OCR-0\skills\xiaomi-ocr\.venv\Scripts\python.exe" set "PY=..\Xiaomi-OCR-0\skills\xiaomi-ocr\.venv\Scripts\python.exe"
if not defined PY if exist "Xiaomi-OCR-0\skills\xiaomi-ocr\.venv\Scripts\python.exe" set "PY=Xiaomi-OCR-0\skills\xiaomi-ocr\.venv\Scripts\python.exe"

if not defined PY (
  echo [x] 找不到 Python。请安装 Python 3.10+ 并加入 PATH。
  pause
  exit /b 1
)

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
pause
