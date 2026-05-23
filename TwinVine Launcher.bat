@echo off
cd /d "%~dp0"

:: ── If venv exists, use its pythonw (correct version, real binary from uv) ───
if exist "%~dp0TwinVine\.venv\Scripts\pythonw.exe" (
    start "" "%~dp0TwinVine\.venv\Scripts\pythonw.exe" "%~dp0twinvine_launcher.py"
    exit /b
)
if exist "%~dp0TwinVine\.venv\Scripts\python.exe" (
    start "" /b "%~dp0TwinVine\.venv\Scripts\python.exe" "%~dp0twinvine_launcher.py"
    exit /b
)

:: ── First run: no venv yet — find a real Python (not a Microsoft Store stub) ──
:: Store stubs are 0-byte files in WindowsApps — skip them.
set "PYTHON="

:: Check all pythonw locations, skip 0-byte Store stubs
for /f "delims=" %%i in ('where pythonw 2^>nul') do (
    if "%%i" neq "" (
        for %%S in ("%%i") do (
            if %%~zS gtr 0 (
                if not defined PYTHON set "PYTHON=%%i"
            )
        )
    )
)
if defined PYTHON goto :have_python

:: Check all python locations, skip 0-byte Store stubs
for /f "delims=" %%i in ('where python 2^>nul') do (
    if "%%i" neq "" (
        for %%S in ("%%i") do (
            if %%~zS gtr 0 (
                if not defined PYTHON set "PYTHON=%%i"
            )
        )
    )
)
if defined PYTHON goto :have_python

:: All pythons found are Store stubs
echo.
echo ERROR: No real Python installation found.
echo The Microsoft Store Python (0-byte stub) cannot run this app.
echo.
echo Please install Python from: https://python.org/downloads/
echo Choose the Windows installer (NOT the Microsoft Store version).
echo During installation, tick "Add Python to PATH".
echo.
pause
exit /b 1

:have_python
echo Using Python: %PYTHON%

:: Auto-install PyQt6 if missing
"%PYTHON%" -c "import PyQt6" >nul 2>&1
if errorlevel 1 (
    echo Installing PyQt6 - please wait...
    "%PYTHON%" -m pip install PyQt6 requests --quiet >nul 2>&1
    if errorlevel 1 "%PYTHON%" -m pip install PyQt6 requests --user --quiet >nul 2>&1
)

start "" /b "%PYTHON%" "%~dp0twinvine_launcher.py"
