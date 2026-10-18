# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 单文件打包配置（Airflow）
# 用法: pyinstaller --clean --noconfirm Airflow.spec
# 产物: dist\Airflow.exe

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    # 把整个 uxplay 目录（含 bin/lib/libexec/share 运行时树）内置进单文件 exe，
    # 运行时从 sys._MEIPASS 临时解压目录解析；exe 同目录的外部 uxplay\ 仍可覆盖。
    datas=[('uxplay', 'uxplay'), ('app_icon.ico', '.'), ('deskflow-portable.zip', '.'),
           ('mac', 'mac')],
    hiddenimports=['PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'pydoc'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Airflow',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # 未安装 UPX 时不要依赖它；需要压缩可改为 True
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # 纯 GUI，不带控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app_icon.ico',
)