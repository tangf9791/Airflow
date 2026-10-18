# -*- coding: utf-8 -*-
"""Airflow —— Windows AirPlay 镜像接收器（iPad 投屏接收端）。

核心机制：
  * 启动时在后台拉起开源 uxplay.exe（子进程），接收 iPad 的 AirPlay 镜像；
  * 默认把 uxplay 的视频窗口内嵌进本程序自己的窗口（全屏或窗口模式）；
  * 按 F1 打开设置面板（视频尺寸/画质/帧率、全屏/窗口、设备名、开机自启等）；
  * 按 ESC / Q（全局热键，任何窗口聚焦时都有效）立即安全终止 uxplay 并退出；
  * 捕获窗口关闭事件（Alt+F4），退出时保证 uxplay 进程被清理干净。

设置保存在 %APPDATA%\\iPadScreenReceiver\\config.json；环境变量可临时覆盖。

用法：
  python main.py                 # 内嵌模式（默认）
  python main.py --standalone    # uxplay 自带全屏窗口（等价于 uxplay -fs ...）
  python main.py --no-uxplay     # 不启动 uxplay（仅测试窗口/热键）
  python main.py --smoke 6       # 6 秒后自动退出（自动化测试用）
  python main.py --screenshot a.png  # 启动约 2 秒后保存整屏截图（调试用）
"""

from __future__ import annotations

import ctypes
import os
import re
import shlex
import subprocess
import shutil
import sys
import tempfile
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QProcess, QProcessEnvironment, Qt, QTimer
from PyQt6.QtGui import QGuiApplication, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QHBoxLayout, QLabel, QMenu, QPushButton,
    QSystemTrayIcon, QVBoxLayout, QWidget,
)

from config import APP_NAME, Settings, load_settings, save_settings, set_autostart
from kvm import extract_portable, portable_dir, resolve_deskflow
from lanshare import LanShare
from settings_dialog import SettingsDialog

APP_VERSION = "2.7.3"
LOG_FILE = Path(tempfile.gettempdir()) / "Airflow.log"

VK_F1 = 0x70
VK_F2 = 0x71
VK_F3 = 0x72
VK_F5 = 0x74
IDC_ARROW = 32512


def log(msg: str) -> None:
    r"""极简日志，便于排查（%TEMP%\iPadScreenReceiver.log）。"""
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except OSError:
        pass


def resolve_uxplay() -> Path | None:
    """按优先级查找 uxplay.exe（打包版：外部 uxplay\\ 子目录优先于内置副本）。"""
    env = os.environ.get("UXPLAY_EXE")
    if env and Path(env).is_file():
        return Path(env)
    if getattr(sys, "frozen", False):
        app_dir = Path(sys.executable).resolve().parent
        meipass = Path(getattr(sys, "_MEIPASS", app_dir))
        candidates = [app_dir, app_dir / "uxplay", meipass / "uxplay", Path.cwd()]
    else:
        app_dir = Path(__file__).resolve().parent
        candidates = [app_dir, app_dir / "uxplay", Path.cwd()]
    for d in candidates:
        p = d / "uxplay.exe"
        if p.is_file():
            return p
    found = shutil.which("uxplay.exe")
    return Path(found) if found else None


def gstreamer_env(uxplay_path: Path) -> dict[str, str]:
    """Windows 的 GStreamer 版 uxplay 需要指定插件/扫描器路径。

    若 uxplay.exe 旁边带有 bin/、lib/gstreamer-1.0/ 等目录（常见的
    预编译包布局），就自动补全这些环境变量，否则原样继承系统环境。
    """
    d = uxplay_path.parent
    env: dict[str, str] = {}
    if (d / "bin").is_dir():
        env["PATH"] = str(d / "bin") + os.pathsep + os.environ.get("PATH", "")
    if (d / "lib" / "gstreamer-1.0").is_dir():
        env["GST_PLUGIN_PATH"] = str(d / "lib" / "gstreamer-1.0")
    scanner = d / "libexec" / "gstreamer-1.0" / "gst-plugin-scanner.exe"
    if scanner.is_file():
        env["GST_PLUGIN_SCANNER"] = str(scanner)
    schemas = d / "share" / "glib-2.0" / "schemas"
    if schemas.is_dir():
        env["GSETTINGS_SCHEMA_DIR"] = str(schemas)
    return env


# ================= 禁止自动熄屏 / 休眠 =================
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def set_prevent_sleep(enabled: bool) -> bool:
    """开启/关闭“禁止自动熄屏与系统休眠”。

    必须在程序的存活线程（Qt 主线程）上调用：请求随该线程结束自动释放。
    """
    flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED if enabled else 0)
    ok = bool(kernel32.SetThreadExecutionState(flags))
    log(f"prevent sleep: {enabled} (ok={ok})")
    return ok


# ================= Apple Bonjour 自动安装 =================
def bonjour_installed() -> bool:
    """检查 Bonjour 服务是否已安装。"""
    try:
        res = subprocess.run(
            ["sc", "query", "Bonjour Service"],
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return res.returncode == 0
    except OSError:
        return False


def find_bonjour_msi() -> Path | None:
    app_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    meipass = Path(getattr(sys, "_MEIPASS", app_dir))
    for base in (app_dir, meipass, Path.cwd()):
        p = base / "uxplay" / "third_party" / "Bonjour64.msi"
        if p.is_file():
            return p
    return None


def install_bonjour() -> bool:
    """自动安装 Apple Bonjour（申请管理员权限，静默安装并等待完成）。"""
    msi = find_bonjour_msi()
    if msi is None:
        log("bonjour: installer not found")
        return False
    log(f"bonjour: installing from {msi}")
    args = f'/i "{msi}" /passive /norestart'
    rc = shell32.ShellExecuteW(None, "runas", "msiexec.exe", args, None, 1)
    if rc <= 32:
        log(f"bonjour: launch failed rc={rc}（用户取消或权限不足）")
        return False
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        if bonjour_installed():
            log("bonjour: installed")
            return True
        QApplication.processEvents()
        time.sleep(0.5)
    log("bonjour: install timeout")
    return bonjour_installed()


# ================= Win32 辅助 =================
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32

# 熄屏/休眠抑制（见 set_prevent_sleep）
kernel32.SetThreadExecutionState.argtypes = [ctypes.c_uint]
kernel32.SetThreadExecutionState.restype = ctypes.c_uint

GWL_STYLE = -16
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_POPUP = 0x80000000
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
WM_CLOSE = 0x0010

_EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_enum_callbacks: list = []  # 保持回调引用，防止被 GC

# ---- Win32 函数签名声明：防止 64 位句柄/指针被 ctypes 截断为 32 位 ----
user32.EnumWindows.argtypes = [_EnumWindowsProc, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
user32.SetParent.restype = wintypes.HWND
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.SetWindowPos.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND
shell32.ShellExecuteW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                  wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int]
shell32.ShellExecuteW.restype = ctypes.c_void_p
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.SetCursor.argtypes = [ctypes.c_void_p]
user32.SetCursor.restype = ctypes.c_void_p
user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
user32.LoadCursorW.restype = ctypes.c_void_p
if hasattr(user32, "GetWindowLongPtrW"):
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
else:
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    user32.SetWindowLongW.restype = ctypes.c_long


_ARROW_CURSOR = user32.LoadCursorW(None, IDC_ARROW)


def find_windows_of_pid(pid: int) -> list[int]:
    """返回指定进程拥有的可见顶层窗口 HWND 列表。"""
    if not pid:
        return []
    found: list[int] = []

    @_EnumWindowsProc
    def cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value == pid:
            found.append(hwnd)
        return True

    _enum_callbacks.append(cb)
    try:
        user32.EnumWindows(cb, 0)
    finally:
        _enum_callbacks.remove(cb)
    return found


def get_window_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    n = user32.GetClassNameW(hwnd, buf, 256)
    return buf.value if n else ""


def _get_style(hwnd: int) -> int:
    if hasattr(user32, "GetWindowLongPtrW"):
        return user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
    return user32.GetWindowLongW(hwnd, GWL_STYLE)


def _set_style(hwnd: int, style: int) -> None:
    if hasattr(user32, "SetWindowLongPtrW"):
        user32.SetWindowLongPtrW(hwnd, GWL_STYLE, style)
    else:
        user32.SetWindowLongW(hwnd, GWL_STYLE, style)


def embed_sdl_window(child_hwnd: int, parent_hwnd: int) -> None:
    """把 uxplay（SDL/GStreamer）的视频窗口重新挂到本程序窗口下并铺满。"""
    style = _get_style(child_hwnd)
    style = (style & ~(WS_POPUP | WS_CAPTION | WS_THICKFRAME)) | WS_CHILD | WS_VISIBLE
    _set_style(child_hwnd, style)
    user32.SetParent(child_hwnd, parent_hwnd)
    rect = wintypes.RECT()
    user32.GetClientRect(parent_hwnd, ctypes.byref(rect))
    user32.SetWindowPos(child_hwnd, 0, 0, 0, rect.right, rect.bottom,
                        SWP_NOZORDER | SWP_NOACTIVATE)
    user32.ShowWindow(child_hwnd, 5)  # SW_SHOW


# ================= 全局键盘钩子 =================
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
VK_ESCAPE = 0x1B
VK_Q = 0x51


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),  # ULONG_PTR
    ]


_LowLevelKeyboardProc = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t
)

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, _LowLevelKeyboardProc,
                                     wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                  wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


class GlobalHotkeyHook:
    """低层键盘钩子：ESC/Q 退出；F1 打开设置（即使焦点在 uxplay 窗口里）。"""

    def __init__(self, target_hwnd: int, dialog_check=None, settings_callback=None,
                 uxplay_pid_fn=None, restart_callback=None, present_callback=None,
                 lan_callback=None):
        self._target_hwnd = target_hwnd
        self._dialog_check = dialog_check or (lambda: False)
        self._settings_callback = settings_callback
        self._uxplay_pid_fn = uxplay_pid_fn or (lambda: 0)
        self._restart_callback = restart_callback
        self._present_callback = present_callback
        self._lan_callback = lan_callback
        self._handle = None
        self._proc = _LowLevelKeyboardProc(self._callback)

    def _is_foreground_ours(self) -> bool:
        """仅当前台窗口是本程序或其 uxplay 子进程时才处理热键，
        避免劫持其它应用里的 ESC / Q / F1 按键。"""
        fg = user32.GetForegroundWindow()
        if not fg:
            return True  # 拿不到前台窗口时保守放行
        if fg == self._target_hwnd:
            return True
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(fg, ctypes.byref(wpid))
        return wpid.value == self._uxplay_pid_fn()

    def _callback(self, n_code, w_param, l_param):
        if n_code == 0 and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
            if self._dialog_check():
                # 设置对话框打开时，把按键让给对话框处理（如 ESC 关闭对话框）
                return user32.CallNextHookEx(self._handle, n_code, w_param, l_param)
            if self._is_foreground_ours():
                info = ctypes.cast(l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
                if info.vkCode == VK_F1 and self._settings_callback:
                    # 只置标志位，由主循环异步打开设置，避免在钩子回调里直接操作 Qt
                    self._settings_callback()
                    return 1  # 吞掉按键
                if info.vkCode == VK_F5 and self._restart_callback:
                    self._restart_callback()
                    return 1
                if info.vkCode == VK_F2 and self._present_callback:
                    self._present_callback()
                    return 1
                if info.vkCode == VK_F3 and self._lan_callback:
                    self._lan_callback()
                    return 1
                if info.vkCode in (VK_ESCAPE, VK_Q):
                    user32.PostMessageW(self._target_hwnd, WM_CLOSE, 0, 0)
                    return 1
        return user32.CallNextHookEx(self._handle, n_code, w_param, l_param)

    def install(self) -> bool:
        if self._handle:
            return True
        self._handle = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._proc, kernel32.GetModuleHandleW(None), 0
        )
        ok = bool(self._handle)
        log(f"global hotkey hook installed: {ok}")
        return ok

    def uninstall(self) -> None:
        if self._handle:
            user32.UnhookWindowsHookEx(self._handle)
            self._handle = None


# ================= 快速选择窗口 =================
class QuickChooser(QDialog):
    """客户端连接时的快速呈现方式选择窗口（可点击、可键盘操作、自动消失）。"""

    def __init__(self, on_choose):
        super().__init__(
            None,
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setObjectName("quickChooser")
        self.setModal(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._on_choose = on_choose
        self.setStyleSheet(
            "QDialog#quickChooser { background:#26262a; border:1px solid #3d3d44; }"
            "QPushButton { background:#3d5afe; border:none; border-radius:6px;"
            " padding:8px 18px; color:white; font-size:13px; min-width:100px; }"
            "QPushButton:hover { background:#5668ff; }"
            "QPushButton:pressed { background:#2f47d6; }"
            "QLabel#quickTitle { color:#e8e8e8; font-size:13px; }"
            "QLabel#quickHint { color:#9a9a9a; font-size:12px; }"
            "QCheckBox { color:#bbb; font-size:12px; }"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        self._title = QLabel("客户端已连接")
        self._title.setObjectName("quickTitle")
        root.addWidget(self._title)
        self._hint = QLabel("")
        self._hint.setObjectName("quickHint")
        self._hint.setWordWrap(True)
        root.addWidget(self._hint)
        row = QHBoxLayout()
        b1 = QPushButton("全屏镜像")
        b2 = QPushButton("扩展屏 (1:1)")
        b1.clicked.connect(lambda: self._choose("fullscreen"))
        b2.clicked.connect(lambda: self._choose("native"))
        row.addWidget(b1)
        row.addWidget(b2)
        root.addLayout(row)
        self._remember = QCheckBox("记住为该客户端类型的默认")
        root.addWidget(self._remember)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(30000)
        self._hide_timer.timeout.connect(self.hide)

    def ask(self, text: str, hint: str, screen) -> None:
        self._title.setText(text)
        self._hint.setText(hint)
        self.adjustSize()
        if screen is not None:
            geo = screen.availableGeometry()
            self.move(geo.left() + 16, geo.top() + 16)
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self._hide_timer.start()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_1:
            self._choose("fullscreen")
            event.accept()
            return
        if key == Qt.Key.Key_2:
            self._choose("native")
            event.accept()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # 回车 = 保持当前预设（不改变画面）
            self.hide()
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
            return
        super().keyPressEvent(event)

    def _choose(self, mode: str) -> None:
        self.hide()
        self._on_choose(mode, self._remember.isChecked())


# ================= 状态角标 =================
class StatusOverlay(QWidget):
    """投屏状态角标：独立置顶小窗，浮在视频上方，不抢焦点、鼠标可穿透。"""

    def __init__(self):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._label = QLabel(self)
        self._label.setStyleSheet(
            "background:rgba(0,0,0,170); color:#e8e8e8; border-radius:8px;"
            " padding:6px 12px; font-family:'Microsoft YaHei'; font-size:13px;"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._label)

    def set_text(self, text: str) -> None:
        if text != self._label.text():
            self._label.setText(text)
            self.adjustSize()

    def place(self, screen) -> None:
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.adjustSize()
        self.move(geo.right() - self.width() - 16, geo.top() + 16)


# ================= 主窗口 =================
class ReceiverWindow(QWidget):
    def __init__(self, settings: Settings, no_uxplay: bool = False,
                 smoke_seconds: int | None = None, screenshot: str | None = None):
        super().__init__()
        self._settings = settings
        self._no_uxplay = no_uxplay
        self._smoke_seconds = smoke_seconds
        self._screenshot = screenshot
        self._shutting_down = False
        self._restarting = False
        self._dialog_open = False
        self._child_hwnd: int = 0
        self._proc: QProcess | None = None
        self._hook: GlobalHotkeyHook | None = None
        self._restart_requested = False
        self._connected = False
        self._connected_at: datetime | None = None
        self._client_type = "other"
        self._stream_size: tuple[int, int] | None = None
        self._active_present = "fullscreen"
        self._present_requested = False
        self._lan_requested = False
        self._chooser = None
        self._kvm_proc: QProcess | None = None
        self._lan = LanShare()
        self._bonjour_ok = True
        self._tray: QSystemTrayIcon | None = None
        self._cursor_hidden = False
        self._last_cursor: tuple[int, int] | None = None
        self._cursor_idle_since = time.monotonic()

        self.setWindowTitle(APP_NAME)
        self.setStyleSheet("background-color: #000000;")
        self.setWindowIcon(self._load_app_icon())

        self._status = QLabel(self)
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet(
            "color:#c9c9c9; font-size:22px; font-family:'Microsoft YaHei';"
            " background:transparent;"
        )
        self._lan_label = QLabel(self)
        self._lan_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lan_label.setStyleSheet(
            "color:#7dd3fc; font-size:18px; font-family:'Microsoft YaHei';")
        self._lan_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._lan_label.hide()

        self._lan_btn = QPushButton("复制下载链接（F3）", self)
        self._lan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lan_btn.setFixedWidth(240)
        self._lan_btn.setStyleSheet(
            "QPushButton{color:#fff;background:#3d5afe;border:none;"
            "border-radius:8px;padding:8px 18px;font-size:15px;}"
            "QPushButton:hover{background:#5668ff;}")
        self._lan_btn.hide()
        self._lan_btn.clicked.connect(self._copy_lan_link)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(self._status)
        layout.addSpacing(14)
        layout.addWidget(self._lan_label)
        layout.addWidget(self._lan_btn, alignment=Qt.AlignmentFlag.AlignHCenter)

        # 轮询查找并内嵌 uxplay 的视频窗口（SDL 版启动即建窗；
        # GStreamer 版要等客户端连接后才建窗，所以持续轮询）
        self._embed_timer = QTimer(self)
        self._embed_timer.setInterval(500)
        self._embed_timer.timeout.connect(self._try_embed)

        # 轮询“请求打开设置 / 重启”标志（全局钩子只置标志，不直接操作 Qt）
        self._settings_requested = False
        self._settings_timer = QTimer(self)
        self._settings_timer.setInterval(200)
        self._settings_timer.timeout.connect(self._check_settings_request)

        # 投屏状态角标
        self._overlay = StatusOverlay()
        self._overlay_timer = QTimer(self)
        self._overlay_timer.setInterval(1000)
        self._overlay_timer.timeout.connect(self._update_overlay)

        # 闲置隐藏鼠标指针
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setInterval(200)
        self._cursor_timer.timeout.connect(self._tick_cursor)

    # ---------- 启动 ----------
    def start(self) -> None:
        _ = self.winId()  # 先确保原生窗口句柄存在（热键、内嵌都要用）
        self._apply_display_mode()
        if self._screenshot:
            QTimer.singleShot(2000, lambda: self._save_screenshot(self._screenshot))
        if self._smoke_seconds:
            QTimer.singleShot(self._smoke_seconds * 1000,
                              lambda: self.shutdown("smoke test timeout"))

        self._settings_timer.start()
        self._setup_tray()
        self._overlay_timer.start()
        self._cursor_timer.start()
        if not self._no_uxplay:
            self._ensure_bonjour()
        self._ensure_lan_share()
        self._update_lan_ui()
        if self._no_uxplay:
            self._status.setText("测试模式：已跳过 uxplay 启动\n\n按 ESC 或 Q 退出")
            return
        self._launch_uxplay()
        self._start_kvm()

    def _target_screen(self):
        """按设置返回全屏使用的显示器（越界时回退主显示器）。"""
        screens = QGuiApplication.screens()
        if not screens:
            return None
        idx = self._settings.monitor_index
        return screens[idx] if 0 <= idx < len(screens) else screens[0]

    def _apply_display_mode(self) -> None:
        """按设置应用全屏/窗口、置顶与显示器（首次启动与设置变更时调用）。"""
        s = self._settings
        fullscreen = s.display_mode == "fullscreen"
        flags = (Qt.WindowType.WindowStaysOnTopHint
                 if (fullscreen or s.always_on_top) else Qt.WindowType(0))
        if fullscreen:
            flags |= Qt.WindowType.FramelessWindowHint
        self.setWindowFlags(flags)
        screen = self._target_screen()
        if fullscreen:
            if screen is not None:
                self.setGeometry(screen.geometry())
            self.showFullScreen()
        else:
            self.showNormal()
            if s.remember_window:
                self.setGeometry(*s.window_rect)
            else:
                self.resize(1280, 720)
        log(f"display mode: {s.display_mode} always_on_top={s.always_on_top} "
            f"monitor={s.monitor_index}")

    # ---------- uxplay 生命周期 ----------
    def _current_args(self) -> list[str]:
        raw = os.environ.get("UXPLAY_ARGS")
        if raw:
            return shlex.split(raw)  # 完全自定义（调试用）
        return self._settings.uxplay_args()

    # ---------- Bonjour / 键盘共享 ----------
    def _ensure_bonjour(self) -> None:
        """确保 Apple Bonjour 可用（缺失时自动安装）。"""
        self._bonjour_ok = bonjour_installed()
        if self._bonjour_ok:
            log("bonjour: installed")
            return
        log("bonjour: not installed, auto-installing")
        self._status.setText(
            "首次运行：正在自动安装 Apple Bonjour…\n"
            "如弹出「用户账户控制」，请点击「是」。\n"
            "安装完成后会自动继续，无需操作。")
        QApplication.processEvents()
        self._bonjour_ok = install_bonjour()
        log(f"bonjour: auto-install ok={self._bonjour_ok}")

    def _ensure_lan_share(self) -> None:
        """局域网分享只在“键盘共享 + 局域网分享”都开启时提供。"""
        if not (self._settings.kvm_enabled and self._settings.lan_share):
            if self._lan.running:
                self._lan.stop()
                log("lan share stopped (kvm/lan disabled)")
            return
        ok, msg = self._lan.start()
        log(f"lan share: {msg if ok else 'failed: ' + msg}")

    def _lan_hint(self) -> str:
        if self._lan.running:
            return f"\nMac 客户端下载：{self._lan.url()}"
        return ""

    def _start_kvm(self) -> None:
        """按设置启动 Deskflow（键盘共享）。"""
        if not self._settings.kvm_enabled:
            return
        if (self._kvm_proc is not None
                and self._kvm_proc.state() != QProcess.ProcessState.NotRunning):
            return
        exe, source = resolve_deskflow(self._settings.deskflow_path)
        if exe is None:
            log("kvm: deskflow not found")
            return
        log(f"kvm: starting deskflow ({source}) {exe}")
        self._kvm_proc = QProcess(self)
        self._kvm_proc.setProgram(str(exe))
        self._kvm_proc.setWorkingDirectory(str(exe.parent))
        self._kvm_proc.start()

    def _stop_kvm(self) -> None:
        proc = self._kvm_proc
        if proc is not None and proc.state() != QProcess.ProcessState.NotRunning:
            log("kvm: stopping deskflow")
            proc.terminate()
            if not proc.waitForFinished(3000):
                proc.kill()
                proc.waitForFinished(1500)
        self._kvm_proc = None

    def _launch_uxplay(self) -> None:
        exe = resolve_uxplay()
        if exe is None:
            self._status.setText(
                "未找到 uxplay.exe\n请把它放到本程序同目录、uxplay\\ 子目录或 PATH 中"
            )
            QTimer.singleShot(5000, self.shutdown)
            return

        args = self._current_args()
        log(f"launch: {exe} {' '.join(args)}")
        proc = QProcess(self)
        proc.setProgram(str(exe))
        proc.setArguments(args)
        proc.setWorkingDirectory(str(exe.parent))
        gst_env = gstreamer_env(exe)
        if gst_env:
            penv = QProcessEnvironment.systemEnvironment()
            for k, v in gst_env.items():
                penv.insert(k, v)
            proc.setProcessEnvironment(penv)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        proc.readyReadStandardOutput.connect(lambda p=proc: self._on_uxplay_output(p))
        proc.finished.connect(lambda code, st, p=proc: self._on_uxplay_finished(code, st, p))
        proc.errorOccurred.connect(lambda err, p=proc: self._on_uxplay_error(err, p))
        proc.start()
        self._proc = proc
        self._connected = False
        self._connected_at = None
        self._client_type = "other"
        self._stream_size = None
        self._active_present = "fullscreen"
        if self._chooser is not None:
            self._chooser.hide()

        warn = "" if self._bonjour_ok else "\n⚠ Apple Bonjour 未就绪，iPad 可能搜不到本机"
        self._status.setText(
            f"等待 iPad 投屏连接…{warn}\n设备名：{self._settings.device_name}\n\n"
            f"按 F1 设置 · F5 重启投屏 · 按 ESC 或 Q 退出"
        )
        self._update_lan_ui()
        if self._settings.standalone:
            # uxplay 使用自带全屏窗口，本窗口隐藏，只负责生命周期与全局热键
            QTimer.singleShot(1200, self.hide)
        else:
            self._embed_timer.start()

    def _stop_uxplay(self) -> None:
        """终止 uxplay：先发 WM_CLOSE 优雅退出，超时再强杀。"""
        proc = self._proc
        if proc and proc.state() != QProcess.ProcessState.NotRunning:
            pid = int(proc.processId())
            if pid:
                for hwnd in find_windows_of_pid(pid):
                    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                # 内嵌后视频窗不再是顶层窗口，EnumWindows 找不到，需单独发
                if self._child_hwnd and user32.IsWindow(self._child_hwnd):
                    user32.PostMessageW(self._child_hwnd, WM_CLOSE, 0, 0)
            if not proc.waitForFinished(1200):
                log("uxplay did not exit gracefully, force killing")
                proc.kill()
                proc.waitForFinished(800)
        self._proc = None
        self._child_hwnd = 0

    def restart_uxplay(self, reason: str = "") -> None:
        """设置变更后重启投屏服务。"""
        log(f"restart uxplay: {reason}")
        self._restarting = True
        try:
            self._status.show()
            self._status.setText("正在应用设置…\n正在重启投屏服务…")
            self._stop_uxplay()
            self._launch_uxplay()
        finally:
            self._restarting = False

    # ---------- 设置 ----------
    def open_settings(self) -> None:
        if self._dialog_open:
            return
        self._dialog_open = True
        try:
            dlg = SettingsDialog(
                self._settings, self,
                version=APP_VERSION,
                uxplay_path=str(resolve_uxplay() or ""),
                log_file=str(LOG_FILE),
                lan_url=self._lan.url() if self._lan.running else "",
            )
            if dlg.exec():
                new = dlg.result_settings()
                old = self._settings
                log(f"settings applied: name={new.device_name} "
                    f"size={new.video_size} quality={new.video_quality} "
                    f"fps={new.fps} display={new.display_mode} "
                    f"top={new.always_on_top} standalone={new.standalone} "
                    f"monitor={new.monitor_index} audio={new.audio_enabled} "
                    f"flip={new.flip_mode} rotate={new.rotate_mode}")
                args_changed = old.uxplay_args() != new.uxplay_args()
                display_changed = (old.display_mode != new.display_mode
                                   or old.always_on_top != new.always_on_top
                                   or old.standalone != new.standalone
                                   or old.monitor_index != new.monitor_index)
                autostart_changed = old.auto_start != new.auto_start
                sleep_changed = old.prevent_sleep != new.prevent_sleep
                tray_changed = old.tray_enabled != new.tray_enabled
                self._settings = new
                save_settings(new)
                if autostart_changed:
                    set_autostart(new.auto_start)
                    log(f"auto start set to {new.auto_start}")
                if sleep_changed:
                    set_prevent_sleep(new.prevent_sleep)
                if tray_changed:
                    if new.tray_enabled:
                        self._setup_tray()
                    elif self._tray is not None:
                        self._tray.hide()
                        self._tray = None
                        log("tray icon removed")
                if old.kvm_enabled != new.kvm_enabled:
                    if new.kvm_enabled:
                        self._start_kvm()
                    else:
                        self._stop_kvm()
                if old.lan_share != new.lan_share or old.kvm_enabled != new.kvm_enabled:
                    self._ensure_lan_share()
                self._update_lan_ui()
                self._status.setText(
                    f"等待 iPad 投屏连接…\n"
                    f"设备名：{new.device_name}\n\n"
                    f"按 F1 设置 · F5 重启投屏 · 按 ESC 或 Q 退出")
                self._apply_display_mode()
                self._update_overlay()
                if old.ipad_mode != new.ipad_mode or old.mac_mode != new.mac_mode:
                    self._active_present = self._present_mode_for(self._client_type)
                    self._apply_video_layout()
                if args_changed or display_changed:
                    self.restart_uxplay("settings applied")
        finally:
            self._dialog_open = False

    # ---------- 客户端类型 / 画面呈现 ----------
    def _present_mode_for(self, client_type: str) -> str:
        s = self._settings
        if client_type == "mac":
            return s.mac_mode
        if client_type == "ipad":
            return s.ipad_mode
        return "fullscreen"

    def _on_client_connected(self, model: str) -> None:
        """根据 uxplay 输出的客户端型号（如 iPad15,4 / MacBookPro18,1）判定类型。"""
        m = model.lower()
        if m.startswith("mac"):
            self._client_type = "mac"
        elif m.startswith("ipad"):
            self._client_type = "ipad"
        else:
            self._client_type = "other"
        self._active_present = self._present_mode_for(self._client_type)
        log(f"client type: {self._client_type} ({model}) "
            f"present={self._active_present}")
        self._apply_video_layout()
        if self._settings.ask_on_connect:
            self._show_chooser(model)

    def _show_chooser(self, model: str) -> None:
        if self._chooser is None:
            self._chooser = QuickChooser(self._apply_chooser_choice)
        kind = {"mac": "Mac", "ipad": "iPad"}.get(self._client_type, model)
        self._chooser.ask(
            f"检测到 {kind} 已连接 · 本次如何在 PC 上显示？",
            "镜像/扩展由 Mac 端决定，这里只决定 PC 端怎么呈现画面。\n"
            "点击按钮，或按 1 = 全屏镜像，2 = 扩展屏，回车 = 保持默认",
            self._target_screen(),
        )

    def _apply_chooser_choice(self, mode: str, remember: bool) -> None:
        self._active_present = mode
        self._apply_video_layout()
        if remember:
            if self._client_type == "mac":
                self._settings.mac_mode = mode
            elif self._client_type == "ipad":
                self._settings.ipad_mode = mode
            save_settings(self._settings)
        log(f"chooser: mode={mode} remember={remember}")

    def set_present(self, mode: str) -> None:
        self._active_present = mode if mode in ("fullscreen", "native") else "fullscreen"
        log(f"present -> {self._active_present}")
        self._apply_video_layout()

    def toggle_present(self) -> None:
        self.set_present("native" if self._active_present == "fullscreen"
                         else "fullscreen")

    @staticmethod
    def _compute_video_rect(cw: int, ch: int, mode: str,
                            stream: tuple[int, int] | None) -> tuple[int, int, int, int]:
        """计算内嵌视频窗口的 (x, y, w, h)。

        fullscreen：铺满客户区（拉伸）；
        native：按来流分辨率 1:1 居中，超出时等比缩小，不放大。
        """
        if mode == "native" and stream and stream[0] > 1 and stream[1] > 1:
            sw, sh = stream
            scale = min(cw / sw, ch / sh, 1.0)
            w = max(1, int(sw * scale))
            h = max(1, int(sh * scale))
            return (cw - w) // 2, (ch - h) // 2, w, h
        return 0, 0, cw, ch

    def _apply_video_layout(self) -> None:
        if not self._child_hwnd:
            return
        rect = wintypes.RECT()
        user32.GetClientRect(int(self.winId()), ctypes.byref(rect))
        x, y, w, h = self._compute_video_rect(
            rect.right, rect.bottom, self._active_present, self._stream_size)
        user32.SetWindowPos(self._child_hwnd, 0, x, y, w, h,
                            SWP_NOZORDER | SWP_NOACTIVATE)

    # ---------- 窗口内嵌 ----------
    def _pick_embed_target(self, hwnds: list[int]) -> int | None:
        """优先选 SDL 视频窗；其次排除 Qt/托盘相关窗口后取第一个。"""
        for h in hwnds:
            cls = get_window_class(h)
            if cls == "SDL_app":
                return h
        for h in hwnds:
            cls = get_window_class(h)
            if cls.lower().startswith(("qt", "uxplay-windows", "gdk")):
                continue
            return h
        return None

    def _try_embed(self) -> None:
        proc = self._proc
        if not proc or proc.state() == QProcess.ProcessState.NotRunning:
            return
        pid = int(proc.processId())
        if not pid:
            return
        target = self._pick_embed_target(find_windows_of_pid(pid))
        if not target:
            return  # 窗口还没出现，继续轮询
        if target != self._child_hwnd:
            # 重挂载前记录来流分辨率（d3d11videosink 窗口尺寸 = 视频尺寸）
            rect = wintypes.RECT()
            if user32.GetWindowRect(target, ctypes.byref(rect)):
                w, h = rect.right - rect.left, rect.bottom - rect.top
                if w > 1 and h > 1:
                    self._stream_size = (w, h)
            embed_sdl_window(target, int(self.winId()))
            self._child_hwnd = target
            log(f"uxplay video window embedded: hwnd={target:#x} "
                f"stream={self._stream_size} present={self._active_present}")
            self._status.hide()
            self._lan_label.hide()
            self._lan_btn.hide()
            self._apply_video_layout()
        else:
            self._apply_video_layout()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_video_layout()

    # ---------- 按键 / 消息 ----------
    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_F1:
            self.open_settings()
            event.accept()
            return
        if event.key() == Qt.Key.Key_F5:
            self.restart_uxplay("F5 key")
            event.accept()
            return
        if event.key() == Qt.Key.Key_F2:
            self.toggle_present()
            event.accept()
            return
        if event.key() == Qt.Key.Key_F3:
            self._copy_lan_link()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
            self.shutdown("pressed ESC/Q")
            event.accept()
            return
        super().keyPressEvent(event)

    def _check_settings_request(self) -> None:
        if self._lan_requested:
            self._lan_requested = False
            self._copy_lan_link()
            return
        if self._present_requested:
            self._present_requested = False
            self.toggle_present()
            return
        if self._restart_requested:
            self._restart_requested = False
            self.restart_uxplay("F5")
            return
        if self._settings_requested:
            self._settings_requested = False
            self.open_settings()

    def closeEvent(self, event) -> None:
        if self._settings.minimize_to_tray and self._tray is not None:
            self.hide()
            event.ignore()
            log("window hidden to tray")
            return
        self.shutdown("window closed (Alt+F4)")
        event.accept()

    # ---------- uxplay 进程回调 ----------
    def _on_uxplay_output(self, proc) -> None:
        data = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace").strip()
        if not data:
            return
        log("uxplay: " + data)
        if "connection request from" in data:
            mo = re.search(r"connection request from .*?\(([^)]+)\)", data)
            if mo:
                self._on_client_connected(mo.group(1))
        if not self._connected and ("Begin streaming" in data
                                    or "connection request from" in data):
            self._connected = True
            self._connected_at = datetime.now()
            log("client connected")
            if self._settings.connect_sound:
                self._play_connect_sound()

    def _on_uxplay_error(self, error, proc) -> None:
        log(f"uxplay error: {error}")
        if self._shutting_down or proc is not self._proc:
            return  # 退出/重启期间的旧进程事件，忽略
        if error == QProcess.ProcessError.FailedToStart:
            self._status.setText(
                "uxplay 启动失败\n请确认 uxplay.exe 及其依赖（如 Bonjour）已就绪\n\n"
                "按 F1 修改设置后重试，或按 ESC / Q 退出"
            )

    def _on_uxplay_finished(self, exit_code: int, exit_status, proc) -> None:
        log(f"uxplay exited: code={exit_code} status={exit_status}")
        if self._shutting_down or self._restarting:
            return  # 退出中 / 重启期间旧进程退出，忽略
        if proc is not self._proc:
            return  # 非当前进程的退出事件（旧进程），忽略
        self._proc = None
        self._child_hwnd = 0
        self._status.show()
        hint = ""
        if exit_code != 0:
            hint = "\n可检查设置面板中的参数，或查看日志定位原因"
        self._status.setText(
            f"uxplay 已退出（代码 {exit_code}）{hint}\n\n"
            f"按 F1 修改设置后重新应用，或按 ESC / Q 退出"
        )
        # 不自动退出：保留程序供用户调整设置后重启服务

    # ---------- 截图（调试） ----------
    def _save_screenshot(self, path: str) -> None:
        try:
            screen = QGuiApplication.primaryScreen()
            if screen:
                screen.grabWindow(0).save(path)
                log(f"screenshot saved: {path}")
        except Exception as exc:  # noqa: BLE001
            log(f"screenshot failed: {exc}")

    # ---------- 图标 / 托盘 ----------
    @staticmethod
    def _load_app_icon() -> QIcon:
        candidates = []
        if getattr(sys, "frozen", False):
            candidates.append(Path(sys.executable).parent / "app_icon.ico")
            candidates.append(Path(getattr(sys, "_MEIPASS", "")) / "app_icon.ico")
        candidates.append(Path(__file__).resolve().parent / "app_icon.ico")
        for p in candidates:
            if p.is_file():
                return QIcon(str(p))
        pm = QPixmap(64, 64)
        pm.fill(Qt.GlobalColor.transparent)
        return QIcon(pm)

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            log("tray icon: system tray unavailable")
            return
        if self._tray is None:
            self._tray = QSystemTrayIcon(self._load_app_icon(), self)
            menu = QMenu()
            menu.addAction("显示主窗口", self._show_from_tray)
            menu.addAction("设置 (F1)", self.open_settings)
            menu.addAction("重启投屏服务 (F5)", lambda: self.restart_uxplay("tray"))
            menu.addAction("显示方式：全屏拉伸", lambda: self.set_present("fullscreen"))
            menu.addAction("显示方式：1:1 扩展", lambda: self.set_present("native"))
            menu.addAction("复制 Mac 客户端下载链接", self._copy_lan_link)
            menu.addSeparator()
            menu.addAction("退出", lambda: self.shutdown("tray quit"))
            self._tray.setContextMenu(menu)
            self._tray.setToolTip(f"{APP_NAME} · 按 F1 设置")
            self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()
        log("tray icon shown")

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_from_tray()

    def _update_lan_ui(self) -> None:
        enabled = self._settings.kvm_enabled and self._settings.lan_share
        if enabled and self._lan.running and not self._shutting_down:
            url = self._lan.url()
            self._lan_label.setText(
                f"Mac 客户端下载：{url}\n"
                f"在 Mac 的浏览器地址栏输入上面的网址即可下载")
            self._lan_label.show()
            self._lan_btn.show()
        else:
            self._lan_label.hide()
            self._lan_btn.hide()

    def _restore_idle_status(self) -> None:
        if self._shutting_down:
            return
        warn = "" if self._bonjour_ok else "\n⚠ Apple Bonjour 未就绪"
        self._status.setText(
            f"等待 iPad 投屏连接…{warn}\n设备名：{self._settings.device_name}\n\n"
            f"按 F1 设置 · F5 重启投屏 · 按 ESC 或 Q 退出")

    def _copy_lan_link(self) -> None:
        if not self._lan.running:
            self._status.setText(
                "局域网分享未开启\n请在 设置 → 键盘共享 中勾选「局域网分享」并保存")
            QTimer.singleShot(5000, self._restore_idle_status)
            return
        url = self._lan.url()
        QApplication.clipboard().setText(url)
        log(f"lan share: copied {url}")
        self._status.setText(
            f"已复制下载链接\n\n{url}\n\n"
            f"在 Mac 的浏览器地址栏输入这个网址即可下载")
        QTimer.singleShot(6000, self._restore_idle_status)

    def _show_from_tray(self) -> None:
        self._apply_display_mode()
        self.raise_()
        self.activateWindow()

    def _play_connect_sound(self) -> None:
        try:
            import winsound
            winsound.PlaySound("SystemNotification",
                               winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:  # noqa: BLE001
            pass

    # ---------- 状态角标 / 鼠标指针 ----------
    def _update_overlay(self) -> None:
        if (not self._settings.status_overlay or not self.isVisible()
                or self._dialog_open):
            self._overlay.hide()
            return
        s = self._settings
        state = "投屏中" if self._connected else "等待连接"
        if self._connected and self._connected_at is not None:
            secs = max(0, int((datetime.now() - self._connected_at).total_seconds()))
            state += f" {secs // 3600:02d}:{secs % 3600 // 60:02d}:{secs % 60:02d}"
        size = "原机" if s.video_size == "auto" else s.video_size
        fps = "默认" if s.fps == 30 else str(s.fps)
        self._overlay.set_text(
            f"{s.device_name} · {size} @ {fps}fps · {state}")
        self._overlay.place(self._target_screen())
        if not self._overlay.isVisible():
            self._overlay.show()

    def _tick_cursor(self) -> None:
        """全屏 + 前台是本程序时，闲置 2 秒自动隐藏鼠标指针。"""
        active = (self._settings.hide_cursor
                  and self._settings.display_mode == "fullscreen"
                  and self.isVisible()
                  and user32.GetForegroundWindow() == int(self.winId()))
        if not active:
            if self._cursor_hidden:
                user32.SetCursor(_ARROW_CURSOR)
                self._cursor_hidden = False
            return
        pt = wintypes.POINT()
        if not user32.GetCursorPos(ctypes.byref(pt)):
            return
        pos = (pt.x, pt.y)
        now = time.monotonic()
        if self._last_cursor != pos:
            self._last_cursor = pos
            self._cursor_idle_since = now
            if self._cursor_hidden:
                user32.SetCursor(_ARROW_CURSOR)
                self._cursor_hidden = False
        elif not self._cursor_hidden and now - self._cursor_idle_since > 2.0:
            user32.SetCursor(None)
            self._cursor_hidden = True
            log("cursor hidden")

    def _save_window_rect(self) -> None:
        if (self._settings.display_mode == "windowed"
                and self._settings.remember_window):
            g = self.geometry()
            self._settings.window_rect = [g.x(), g.y(), g.width(), g.height()]
            save_settings(self._settings)

    # ---------- 安全退出 ----------
    def shutdown(self, reason: str = "") -> None:
        """终止 uxplay 并退出程序（幂等，可被多次调用）。"""
        if self._shutting_down:
            return
        self._shutting_down = True
        log(f"shutdown: {reason or 'requested'}")
        self._embed_timer.stop()
        self._settings_timer.stop()
        self._overlay_timer.stop()
        self._cursor_timer.stop()
        if self._cursor_hidden:
            user32.SetCursor(_ARROW_CURSOR)
            self._cursor_hidden = False
        self._overlay.hide()
        if self._chooser is not None:
            self._chooser.hide()
        if self._tray is not None:
            self._tray.hide()
        self._save_window_rect()
        if self._hook:
            self._hook.uninstall()
        self._stop_kvm()
        self._lan.stop()
        self._stop_uxplay()
        set_prevent_sleep(False)  # 释放熄屏/休眠抑制
        log("shutdown complete")
        app = QApplication.instance()
        if app:
            app.quit()


# ================= 入口 =================
def main() -> int:
    settings = load_settings()
    if "--standalone" in sys.argv:
        settings.standalone = True  # 仅本次运行生效
    no_uxplay = "--no-uxplay" in sys.argv
    smoke_seconds: int | None = None
    if "--smoke" in sys.argv:
        try:
            smoke_seconds = int(sys.argv[sys.argv.index("--smoke") + 1])
        except (ValueError, IndexError):
            smoke_seconds = 6
    screenshot = None
    if "--screenshot" in sys.argv:
        try:
            screenshot = sys.argv[sys.argv.index("--screenshot") + 1]
        except IndexError:
            screenshot = None
    set_prevent_sleep(settings.prevent_sleep)  # 主线程上申请，随进程存活
    log(f"mode: standalone={settings.standalone} no_uxplay={no_uxplay} "
        f"smoke={smoke_seconds} display={settings.display_mode} "
        f"size={settings.video_size} quality={settings.video_quality} fps={settings.fps}")

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    window = ReceiverWindow(settings, no_uxplay, smoke_seconds, screenshot)
    window._hook = GlobalHotkeyHook(
        int(window.winId()),
        dialog_check=lambda: window._dialog_open,
        settings_callback=lambda: setattr(window, "_settings_requested", True),
        restart_callback=lambda: setattr(window, "_restart_requested", True),
        present_callback=lambda: setattr(window, "_present_requested", True),
        lan_callback=lambda: setattr(window, "_lan_requested", True),
        uxplay_pid_fn=lambda: (int(window._proc.processId())
                               if window._proc
                               and window._proc.state() != QProcess.ProcessState.NotRunning
                               else 0),
    )
    window._hook.install()

    window.start()
    rc = app.exec()
    window.shutdown("app quit")
    return rc


if __name__ == "__main__":
    sys.exit(main())