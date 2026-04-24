@echo off
:: build.bat - Run this on Windows to compile GitManager.exe
:: Requirements: Python 3.9+, pip install pyinstaller

echo ========================================
echo  Git Manager - Build Script
echo ========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    echo Download from https://python.org
    pause
    exit /b 1
)

:: Check git
git --version >nul 2>&1
if errorlevel 1 (
    echo WARNING: git not found in PATH. The app needs git to run.
    echo Download from https://git-scm.com
)

:: Install PyInstaller
echo Installing PyInstaller...
python -m pip install pyinstaller --quiet
if errorlevel 1 (
    echo ERROR: Failed to install PyInstaller.
    pause
    exit /b 1
)

:: Build using python -m (avoids PATH issues)
echo.
echo Building GitManager.exe ...
python -m PyInstaller --noconfirm --clean ^
    --onefile ^
    --windowed ^
    --name GitManager ^
    gitmanager.py

if errorlevel 1 (
    echo.
    echo BUILD FAILED. Check errors above.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  SUCCESS!
echo  Executable: dist\GitManager.exe
echo ========================================
pause
