# -*- coding: utf-8 -*-
"""Deskflow（键盘共享 / KVM）集成辅助：查找、解压、检测可执行文件。"""

from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path

from config import APP_NAME

BUNDLE_ZIP_NAME = "deskflow-portable.zip"


def portable_dir() -> Path:
    """解压后的 Deskflow 便携目录。"""
    return Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME / "deskflow"


def find_bundle_zip() -> Path | None:
    app_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    meipass = Path(getattr(sys, "_MEIPASS", app_dir))
    for base in (app_dir, meipass, Path.cwd()):
        p = base / BUNDLE_ZIP_NAME
        if p.is_file():
            return p
    return None


def portable_exe() -> Path | None:
    """已解压的 deskflow.exe（兼容压缩包内多一层目录）。"""
    d = portable_dir()
    if not d.is_dir():
        return None
    candidates = [d / "deskflow.exe"]
    try:
        candidates += [p / "deskflow.exe" for p in d.iterdir() if p.is_dir()]
    except OSError:
        pass
    for p in candidates:
        if p.is_file():
            return p
    return None


def installed_exe() -> Path | None:
    """系统已安装的 Deskflow。"""
    candidates = [
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Deskflow" / "deskflow.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Deskflow" / "deskflow.exe",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def extract_portable() -> Path | None:
    """把内置便携包解压到 %APPDATA%\\Airflow\\deskflow（已存在则直接返回）。"""
    exe = portable_exe()
    if exe is not None:
        return exe
    zip_path = find_bundle_zip()
    if zip_path is None:
        return None
    target = portable_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(target)
    except (OSError, zipfile.BadZipFile):
        return None
    return portable_exe()


def resolve_deskflow(configured: str = "") -> tuple[Path | None, str]:
    """返回 (可执行文件, 来源说明)。优先级：设置路径 > 系统安装 > 内置便携包。"""
    if configured:
        p = Path(configured)
        if p.is_file():
            return p, "设置指定"
    p = installed_exe()
    if p is not None:
        return p, "系统已安装"
    p = extract_portable()
    if p is not None:
        return p, "内置便携版"
    return None, "未找到"
