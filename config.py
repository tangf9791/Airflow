# -*- coding: utf-8 -*-
"""配置管理：设置项定义、JSON 持久化、开机自启动（注册表）。"""

from __future__ import annotations

import json
import os
import shutil
import sys
import winreg
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

APP_NAME = "Airflow"  # 应用名（窗口标题、配置目录、注册表自启项均使用）
CONFIG_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.json"

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = APP_NAME

# ---- 界面下拉框的候选选项 ----
VIDEO_SIZES = [
    ("原机/自动（不指定）", "auto"),
    ("1280 × 720", "1280x720"),
    ("1920 × 1080", "1920x1080"),
    ("2560 × 1440", "2560x1440"),
    ("3840 × 2160（4K，需高画质）", "3840x2160"),
]
VIDEO_QUALITIES = [
    ("标准（H.264）", "standard"),
    ("高（H.265，支持 4K）", "high"),
]
FPS_OPTIONS = [
    ("原机（不指定，默认 30）", 30),
    ("60", 60),
    ("90", 90),
    ("120", 120),
]
DISPLAY_MODES = [
    ("全屏", "fullscreen"),
    ("窗口", "windowed"),
]
# 客户端画面呈现方式（PC 端如何显示收到的视频流）
PRESENT_MODES = [
    ("全屏镜像（拉伸铺满）", "fullscreen"),
    ("扩展屏（1:1 不拉伸）", "native"),
]
FLIP_MODES = [
    ("无", "none"),
    ("水平翻转", "h"),
    ("垂直翻转", "v"),
    ("旋转 180°（倒置）", "i"),
]
ROTATE_MODES = [
    ("无", "none"),
    ("顺时针 90°", "r"),
    ("逆时针 90°", "l"),
]
_VALID = {
    "video_size": {v for _, v in VIDEO_SIZES},
    "video_quality": {v for _, v in VIDEO_QUALITIES},
    "display_mode": {v for _, v in DISPLAY_MODES},
    "flip_mode": {v for _, v in FLIP_MODES},
    "rotate_mode": {v for _, v in ROTATE_MODES},
    "ipad_mode": {v for _, v in PRESENT_MODES},
    "mac_mode": {v for _, v in PRESENT_MODES},
}


@dataclass
class Settings:
    r"""程序设置（持久化到 %APPDATA%\Airflow\config.json）。"""

    device_name: str = "iPad-Screen"
    video_size: str = "auto"           # auto | 1280x720 | 1920x1080 | 2560x1440 | 3840x2160
    video_quality: str = "standard"    # standard | high
    fps: int = 60                      # 30=不指定（uxplay 默认）| 60 | 90 | 120
    display_mode: str = "fullscreen"   # fullscreen | windowed
    always_on_top: bool = True
    standalone: bool = False           # 使用 uxplay 自带全屏窗口（-fs）
    auto_start: bool = False           # 开机自启动（以注册表为准）
    prevent_sleep: bool = True         # 禁止自动熄屏/系统休眠
    monitor_index: int = 0             # 全屏使用的显示器（QGuiApplication.screens() 顺序）
    audio_enabled: bool = True         # 传输音频（关闭时给 uxplay 传 -as 0）
    flip_mode: str = "none"            # none | h | v | i
    rotate_mode: str = "none"          # none | r | l
    hide_cursor: bool = True           # 全屏投屏时闲置自动隐藏鼠标指针
    status_overlay: bool = True        # 显示投屏状态角标
    tray_enabled: bool = True          # 显示托盘图标
    minimize_to_tray: bool = False     # 关闭窗口时最小化到托盘（而不是退出）
    connect_sound: bool = True         # 客户端连上时播放提示音
    remember_window: bool = True       # 记住窗口模式的位置/大小
    window_rect: list = field(default_factory=lambda: [80, 80, 1280, 720])
    ipad_mode: str = "fullscreen"      # iPad 连接时的呈现方式：fullscreen | native
    mac_mode: str = "native"           # Mac 连接时的呈现方式：fullscreen | native
    ask_on_connect: bool = False       # 客户端连接时弹出快速选择窗口
    kvm_enabled: bool = False          # 随程序启动 Deskflow 键盘共享
    lan_share: bool = False            # 局域网分享 Mac 客户端下载页
    deskflow_path: str = ""            # Deskflow 可执行文件路径（空=自动检测/内置）

    def uxplay_args(self) -> list[str]:
        """把设置翻译成 uxplay 命令行参数。"""
        args = ["-n", self.device_name]
        if self.standalone:
            args.append("-fs")
        if self.video_quality == "high":
            args.append("-h265")
        if self.video_size != "auto":
            args += ["-s", self.video_size]
        if self.fps != 30:
            args += ["-fps", str(self.fps)]
        if self.flip_mode in ("h", "v", "i"):
            args += ["-f", self.flip_mode.upper()]
        if self.rotate_mode in ("r", "l"):
            args += ["-r", self.rotate_mode.upper()]
        if not self.audio_enabled:
            args += ["-as", "0"]
        args += ["-vsync", "no"]
        return args


_OLD_APP_NAMES = ("iPadScreenReceiver", "AirMirror")  # 历史应用名（迁移用）


def _migrate_old_config() -> None:
    r"""首次运行 Airflow 时，把历史版本（iPadScreenReceiver / AirMirror）的 config.json 迁移过来。"""
    if CONFIG_FILE.exists():
        return
    appdata = Path(os.environ.get("APPDATA", str(Path.home())))
    for old_name in _OLD_APP_NAMES:
        old = appdata / old_name / "config.json"
        if old.exists():
            try:
                CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                shutil.copy2(old, CONFIG_FILE)
            except OSError:
                pass
            return


def _cleanup_old_autostart() -> None:
    """删除历史应用名的开机自启注册表项（如果存在）。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0,
                            winreg.KEY_SET_VALUE) as key:
            for old_name in _OLD_APP_NAMES:
                try:
                    winreg.DeleteValue(key, old_name)
                except FileNotFoundError:
                    pass
    except OSError:
        pass


def _sanitize(s: Settings) -> Settings:
    """把手工编辑/旧版本配置文件里的非法值收敛到默认值。"""
    for name, allowed in _VALID.items():
        if getattr(s, name) not in allowed:
            setattr(s, name, getattr(Settings(), name))
    if not isinstance(s.fps, int) or s.fps not in (30, 60, 90, 120):
        s.fps = 60
    if not isinstance(s.monitor_index, int) or s.monitor_index < 0:
        s.monitor_index = 0
    rect = s.window_rect
    if not (isinstance(rect, list) and len(rect) == 4
            and all(isinstance(v, int) for v in rect) and rect[2] > 200 and rect[3] > 150):
        s.window_rect = [80, 80, 1280, 720]
    return s


def load_settings() -> Settings:
    """读取配置；环境变量可临时覆盖（测试/临时调整用）。"""
    _migrate_old_config()
    _cleanup_old_autostart()
    s = Settings()
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
        for f in fields(Settings):
            if f.name in data and f.name != "auto_start":
                val = data[f.name]
                if isinstance(val, type(getattr(s, f.name))):
                    setattr(s, f.name, val)
    except (OSError, ValueError):
        pass
    if os.environ.get("UXPLAY_NAME"):
        s.device_name = os.environ["UXPLAY_NAME"]
    if os.environ.get("UXPLAY_FPS"):
        try:
            s.fps = int(os.environ["UXPLAY_FPS"])
        except ValueError:
            pass
    if os.environ.get("UXPLAY_EMBED", "1") == "0":
        s.standalone = True
    s.auto_start = is_autostart_enabled()
    return _sanitize(s)


def save_settings(s: Settings) -> None:
    """保存设置（auto_start 不入文件，以注册表为准）。"""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = asdict(s)
        data.pop("auto_start", None)
        CONFIG_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass


def _autostart_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.is_file() else Path(sys.executable)
    return f'"{exe}" "{Path(sys.argv[0]).resolve()}"'


def is_autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH) as key:
            winreg.QueryValueEx(key, RUN_VALUE)
            return True
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0,
                            winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ,
                                  _autostart_command())
            else:
                try:
                    winreg.DeleteValue(key, RUN_VALUE)
                except FileNotFoundError:
                    pass
    except OSError:
        pass