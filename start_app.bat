@echo off
cd /d "%~dp0"
set PYTHON_EXE=%USERPROFILE%\.venv\Scripts\python.exe
if not exist "%PYTHON_EXE%" (
    set PYTHON_EXE=python
)
start "GPP CDC Data Explorer" "%PYTHON_EXE%" wsgi.py
