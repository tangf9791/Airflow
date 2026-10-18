@echo off
rem 一键打包脚本：安装构建依赖并调用 PyInstaller 生成单文件 exe
setlocal
cd /d "%~dp0"

echo [1/2] Installing build dependencies...
python -m pip install -r requirements-build.txt -q || goto :fail

echo [2/2] Building with PyInstaller...
pyinstaller --clean --noconfirm Airflow.spec || goto :fail

echo.
echo Build OK: %~dp0dist\Airflow.exe  (single file, uxplay embedded)
echo Copy this exe anywhere; it works standalone.
exit /b 0

:fail
echo.
echo BUILD FAILED.
exit /b 1