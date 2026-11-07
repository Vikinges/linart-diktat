@echo off
title LinArt Diktat
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
rem Uses .\venv by default; set LINART_PYTHON to use another interpreter.
set "PY=%~dp0venv\Scripts\pythonw.exe"
if defined LINART_PYTHON set "PY=%LINART_PYTHON%"
start "" "%PY%" "%~dp0diktat.py"
