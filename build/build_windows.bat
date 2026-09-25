@echo off
rem Build APKDeco.exe on Windows (Python 3.9+ required).
rem Usage: build\build_windows.bat
setlocal
cd /d "%~dp0.."

echo === Installing build dependencies ===
py -m pip install --upgrade pyinstaller pillow || goto :error

echo === Running self-test ===
py main.py --selftest || goto :error

echo === Generating icon ===
py build\png2ico.py assets\icon.png assets\icon.ico || goto :error

echo === Building APKDeco.exe ===
py -m PyInstaller --clean --noconfirm build\apkdeco.spec || goto :error

echo.
echo Done: dist\APKDeco.exe
exit /b 0

:error
echo Build FAILED.
exit /b 1
