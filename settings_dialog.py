# -*- coding: utf-8 -*-
"""设置对话框：视频（尺寸/画质/帧率/音频/翻转）、显示（模式/显示器/角标）、常规。"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QProcess, Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QTabWidget,
    QVBoxLayout, QWidget,
)

from config import (
    APP_NAME, DISPLAY_MODES, FLIP_MODES, FPS_OPTIONS, PRESENT_MODES,
    ROTATE_MODES, VIDEO_QUALITIES, VIDEO_SIZES, Settings,
)

_DARK_QSS = """
QDialog { background-color: #202020; color: #e0e0e0; }
QLabel { color: #e0e0e0; }
QLineEdit, QComboBox {
    background-color: #2d2d2d; color: #e0e0e0; border: 1px solid #444;
    border-radius: 4px; padding: 4px 6px; min-height: 20px;
}
QComboBox QAbstractItemView {
    background-color: #2d2d2d; color: #e0e0e0; selection-background-color: #3d5afe;
}
QCheckBox { color: #e0e0e0; spacing: 6px; }
QTabWidget::pane { border: 1px solid #3a3a3a; }
QTabBar::tab { background: #2a2a2a; color: #c0c0c0; padding: 6px 16px; border: 1px solid #3a3a3a; }
QTabBar::tab:selected { background: #3d5afe; color: white; }
QPushButton {
    background-color: #3a3a3a; color: #e0e0e0; border: 1px solid #555;
    border-radius: 4px; padding: 5px 14px;
}
QPushButton:hover { background-color: #4a4a4a; }
QPushButton:default { background-color: #3d5afe; border: none; }
QToolTip { background-color: #2d2d2d; color: #e0e0e0; border: 1px solid #555; }
"""


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None, *, version: str = "",
                 uxplay_path: str = "", log_file: str = "", lan_url: str = ""):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} · 设置")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setStyleSheet(_DARK_QSS)
        self._settings = settings
        self._deskflow_path = settings.deskflow_path

        tabs = QTabWidget(self)

        # ---------------- 视频 ----------------
        video_tab = QWidget()
        vform = QFormLayout(video_tab)
        vform.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.size_combo = QComboBox()
        for label, val in VIDEO_SIZES:
            self.size_combo.addItem(label, val)
        idx = self.size_combo.findData(settings.video_size)
        self.size_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.size_combo.setToolTip(
            "向 iPad 请求的分辨率（AirPlay 实际画质仍由 iPad 决定）；\n"
            "4K 需要配合“高”画质（H.265）。")
        self.size_combo.currentIndexChanged.connect(self._on_size_changed)

        self.quality_combo = QComboBox()
        for label, val in VIDEO_QUALITIES:
            self.quality_combo.addItem(label, val)
        idx = self.quality_combo.findData(settings.video_quality)
        self.quality_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.quality_combo.setToolTip(
            "高 = 启用 H.265 支持，可接收 4K 与更高画质（要求 iPad 支持）。")

        self.fps_combo = QComboBox()
        for label, val in FPS_OPTIONS:
            self.fps_combo.addItem(label, val)
        idx = self.fps_combo.findData(settings.fps)
        self.fps_combo.setCurrentIndex(idx if idx >= 0 else 1)
        self.fps_combo.setToolTip("最大帧率；越高越流畅，但更占用带宽与 CPU。")

        self.audio_check = QCheckBox("传输音频（声音同步到本机）")
        self.audio_check.setChecked(settings.audio_enabled)
        self.audio_check.setToolTip("关闭后给 uxplay 传 -as 0，仅接收画面。")

        self.flip_combo = QComboBox()
        for label, val in FLIP_MODES:
            self.flip_combo.addItem(label, val)
        idx = self.flip_combo.findData(settings.flip_mode)
        self.flip_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.flip_combo.setToolTip("画面翻转：水平 / 垂直 / 旋转 180°（-f H|V|I）。")

        self.rotate_combo = QComboBox()
        for label, val in ROTATE_MODES:
            self.rotate_combo.addItem(label, val)
        idx = self.rotate_combo.findData(settings.rotate_mode)
        self.rotate_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.rotate_combo.setToolTip("画面旋转 90°（-r R|L）。")

        vform.addRow("视频尺寸：", self.size_combo)
        vform.addRow("视频画质：", self.quality_combo)
        vform.addRow("帧率：", self.fps_combo)
        vform.addRow("", self.audio_check)
        vform.addRow("翻转：", self.flip_combo)
        vform.addRow("旋转：", self.rotate_combo)
        hint = QLabel("修改视频设置后会重启投屏服务")
        hint.setStyleSheet("color:#888; font-size:12px;")
        vform.addRow("", hint)

        # ---------------- 显示 ----------------
        display_tab = QWidget()
        dform = QFormLayout(display_tab)
        dform.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.mode_combo = QComboBox()
        for label, val in DISPLAY_MODES:
            self.mode_combo.addItem(label, val)
        idx = self.mode_combo.findData(settings.display_mode)
        self.mode_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.mode_combo.setToolTip("全屏：无边框置顶铺满屏幕；窗口：普通可调整大小的窗口。")
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self.monitor_combo = QComboBox()
        self._screens = QGuiApplication.screens()
        for i, scr in enumerate(self._screens):
            g = scr.geometry()
            label = f"显示器 {i + 1}（{g.width()} × {g.height()}）"
            if i == 0:
                label += " · 主显示器"
            self.monitor_combo.addItem(label, i)
        idx = self.monitor_combo.findData(settings.monitor_index)
        self.monitor_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.monitor_combo.setToolTip("全屏时使用哪块显示器。")

        self.top_check = QCheckBox("窗口总在最前")
        self.top_check.setChecked(settings.always_on_top)
        self.top_check.setEnabled(settings.display_mode == "windowed")

        self.remember_check = QCheckBox("记住窗口模式的位置和大小")
        self.remember_check.setChecked(settings.remember_window)

        self.standalone_check = QCheckBox("使用 uxplay 自带全屏窗口（独立模式）")
        self.standalone_check.setChecked(settings.standalone)
        self.standalone_check.setToolTip(
            "此时本程序窗口隐藏，仅负责全局热键与进程清理；\n"
            "等价于 uxplay -n \"iPad-Screen\" -fs -fps 60 -vsync no。")

        self.ipad_mode_combo = QComboBox()
        for label, val in PRESENT_MODES:
            self.ipad_mode_combo.addItem(label, val)
        idx = self.ipad_mode_combo.findData(settings.ipad_mode)
        self.ipad_mode_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.ipad_mode_combo.setToolTip(
            "iPad 投屏进来时，PC 端如何显示收到的画面。\n"
            "镜像/扩展的选择在 iPad/Mac 端，这里只决定 PC 端的呈现方式。")

        self.mac_mode_combo = QComboBox()
        for label, val in PRESENT_MODES:
            self.mac_mode_combo.addItem(label, val)
        idx = self.mac_mode_combo.findData(settings.mac_mode)
        self.mac_mode_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.mac_mode_combo.setToolTip(
            "Mac 端在 AirPlay 菜单/显示器设置里选「用作单独的显示器」即为扩展屏；\n"
            "扩展屏模式 = 按来流分辨率居中显示、不拉伸，像一块真实显示器。")

        self.ask_check = QCheckBox("客户端连接时弹出快速选择窗口")
        self.ask_check.setChecked(settings.ask_on_connect)

        self.cursor_check = QCheckBox("全屏时闲置自动隐藏鼠标指针")
        self.cursor_check.setChecked(settings.hide_cursor)

        self.overlay_check = QCheckBox("显示投屏状态角标（角落小字）")
        self.overlay_check.setChecked(settings.status_overlay)

        dform.addRow("显示模式：", self.mode_combo)
        dform.addRow("显示器：", self.monitor_combo)
        dform.addRow("", self.top_check)
        dform.addRow("", self.remember_check)
        dform.addRow("", self.standalone_check)
        dform.addRow("iPad 画面呈现：", self.ipad_mode_combo)
        dform.addRow("Mac 画面呈现：", self.mac_mode_combo)
        dform.addRow("", self.ask_check)
        dform.addRow("", self.cursor_check)
        dform.addRow("", self.overlay_check)

        # ---------------- 键盘共享 ----------------
        kvm_tab = QWidget()
        kform = QFormLayout(kvm_tab)
        kform.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.kvm_check = QCheckBox("启用键盘共享（随本程序启动 Deskflow，退出时关闭）")
        self.kvm_check.setChecked(settings.kvm_enabled)
        self.kvm_check.setToolTip(
            "Deskflow 是开源 KVM：用一套键盘鼠标控制多台电脑。\n"
            "启用后本程序会自动启动它，退出时一并关闭。")

        self.kvm_status = QLabel(self._deskflow_status(settings))
        self.kvm_status.setWordWrap(True)
        self.kvm_status.setStyleSheet("color:#9a9a9a; font-size:12px;")

        kvm_btn_row = QHBoxLayout()
        open_btn = QPushButton("打开 Deskflow 界面")
        open_btn.clicked.connect(self._open_deskflow)
        reextract_btn = QPushButton("重新解压内置版")
        reextract_btn.clicked.connect(self._reextract_deskflow)
        mac_btn = QPushButton("生成 Mac 端一键脚本")
        mac_btn.setToolTip("生成一个 .command 脚本：拷到 Mac 上双击即可自动安装并连接本机。")
        mac_btn.clicked.connect(self._generate_mac_client)
        kvm_btn_row.addWidget(open_btn)
        kvm_btn_row.addWidget(reextract_btn)
        kvm_btn_row.addWidget(mac_btn)
        kvm_btn_row.addStretch(1)

        kvm_help = QLabel(
            "使用步骤：\n"
            "1. 点「打开 Deskflow 界面」，本机模式选 Server，把 Mac 添加为一台屏幕（放在本机右侧）；\n"
            "2. Mac 上安装 Deskflow 客户端，填写本机局域网 IP、端口 24800，连接；\n"
            "3. 之后把鼠标移到屏幕右边缘，键盘/鼠标就切换到了 Mac；按 Scroll Lock 可锁定在当前电脑。\n\n"
            "注意：Mac 端首次使用需在「系统设置 → 隐私与安全性 → 辅助功能」里勾选 Deskflow。")
        kvm_help.setWordWrap(True)
        kvm_help.setStyleSheet("color:#bbb; font-size:12px;")

        self.lan_check = QCheckBox("局域网分享（Mac 用浏览器打开网址即可下载客户端）")
        self.lan_check.setChecked(settings.lan_share)
        self.lan_check.setToolTip(
            "开启后本机会在局域网上提供一个只读下载页；\n"
            "Mac 浏览器打开显示的网址即可下载客户端脚本。")

        self.lan_url = QLabel(lan_url or "（保存并应用后开启；地址会显示在等待界面和托盘菜单）")
        self.lan_url.setStyleSheet("color:#7dd3fc; font-size:12px;")
        self.lan_url.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lan_url.setWordWrap(True)

        lan_row = QHBoxLayout()
        copy_btn = QPushButton("复制链接")
        copy_btn.clicked.connect(self._copy_lan_url)
        lan_row.addWidget(self.lan_url, 1)
        lan_row.addWidget(copy_btn)

        kform.addRow("", self.kvm_check)
        kform.addRow("", self.kvm_status)
        kform.addRow("", kvm_btn_row)
        kform.addRow("", kvm_help)
        kform.addRow("", self.lan_check)
        kform.addRow("", lan_row)

        # ---------------- 常规 ----------------
        general_tab = QWidget()
        gform = QFormLayout(general_tab)
        gform.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.name_edit = QLineEdit(settings.device_name)
        self.name_edit.setMaxLength(63)

        self.autostart_check = QCheckBox("登录 Windows 时自动启动本程序")
        self.autostart_check.setChecked(settings.auto_start)

        self.sleep_check = QCheckBox("禁止自动熄屏 / 系统休眠（推荐）")
        self.sleep_check.setChecked(settings.prevent_sleep)
        self.sleep_check.setToolTip(
            "投屏期间保持屏幕常亮、阻止系统进入睡眠；\n"
            "关闭后 Windows 的电源计划会照常让屏幕自动熄灭。")

        self.tray_check = QCheckBox("显示托盘图标")
        self.tray_check.setChecked(settings.tray_enabled)

        self.minimize_check = QCheckBox("关闭窗口时最小化到托盘（不退出）")
        self.minimize_check.setChecked(settings.minimize_to_tray)
        self.minimize_check.setToolTip(
            "开启后 Alt+F4 / 关闭按钮会隐藏到托盘；\n"
            "要彻底退出请用托盘菜单“退出”或按 ESC / Q（本程序窗口在前台时）。")

        self.sound_check = QCheckBox("客户端连接时播放提示音")
        self.sound_check.setChecked(settings.connect_sound)

        about = QLabel(
            f"版本：{version or 'dev'}\n"
            f"uxplay：{uxplay_path or '（未找到）'}\n"
            f"日志：{log_file}\n"
            f"配置：%APPDATA%\\{APP_NAME}\\config.json"
        )
        about.setStyleSheet("color:#999; font-size:12px;")
        about.setWordWrap(True)

        gform.addRow("设备名称：", self.name_edit)
        gform.addRow("", self.autostart_check)
        gform.addRow("", self.sleep_check)
        gform.addRow("", self.tray_check)
        gform.addRow("", self.minimize_check)
        gform.addRow("", self.sound_check)
        gform.addRow("", about)

        tabs.addTab(video_tab, "视频")
        tabs.addTab(display_tab, "显示")
        tabs.addTab(kvm_tab, "键盘共享")
        tabs.addTab(general_tab, "常规")

        # ---------------- 按钮 ----------------
        btn_row = QHBoxLayout()
        reset_btn = QPushButton("恢复默认")
        reset_btn.clicked.connect(self._reset_defaults)
        btn_box = QDialogButtonBox()
        btn_box.addButton("保存并应用", QDialogButtonBox.ButtonRole.AcceptRole)
        btn_box.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_box)

        root = QVBoxLayout(self)
        root.addWidget(tabs)
        root.addLayout(btn_row)

    # ---------------- 交互逻辑 ----------------
    def _on_size_changed(self, _idx: int) -> None:
        # 选 4K 时自动切换到高画质（H.265）
        if self.size_combo.currentData() == "3840x2160":
            self.quality_combo.setCurrentIndex(self.quality_combo.findData("high"))

    def _on_mode_changed(self, _idx: int) -> None:
        self.top_check.setEnabled(self.mode_combo.currentData() == "windowed")

    @staticmethod
    def _deskflow_status(settings: Settings) -> str:
        from kvm import find_bundle_zip, installed_exe, portable_exe
        if installed_exe() is not None:
            return f"Deskflow：系统已安装（{installed_exe()}）"
        if portable_exe() is not None:
            return f"Deskflow：内置便携版已就绪（{portable_exe().parent}）"
        if find_bundle_zip() is not None:
            return ("Deskflow：内置便携版（首次启用时自动解压到 "
                    "%APPDATA%\\Airflow\\deskflow）")
        return "Deskflow：未找到（可手动安装后在 config.json 里设置 deskflow_path）"

    def _open_deskflow(self) -> None:
        from kvm import resolve_deskflow
        exe, _source = resolve_deskflow(self._settings.deskflow_path)
        if exe is None:
            QMessageBox.warning(self, "Deskflow",
                                "未找到 Deskflow，请确认安装包完整或手动安装。")
            return
        QProcess.startDetached(str(exe), [], str(exe.parent))

    def _reextract_deskflow(self) -> None:
        import shutil
        from kvm import extract_portable, portable_dir
        try:
            if portable_dir().exists():
                shutil.rmtree(portable_dir())
        except OSError:
            pass
        exe = extract_portable()
        self.kvm_status.setText(self._deskflow_status(self._settings))
        if exe is None:
            QMessageBox.warning(self, "Deskflow", "解压失败，请检查安装包。")

    def _copy_lan_url(self) -> None:
        text = self.lan_url.text().strip()
        if text.startswith("http"):
            QApplication.clipboard().setText(text)
        else:
            QMessageBox.information(
                self, "局域网分享",
                "开启并「保存并应用」后，地址会显示在这里；\n"
                "也可以从主界面等待页或托盘菜单查看。")

    def _generate_mac_client(self) -> None:
        from PyQt6.QtCore import QStandardPaths
        from PyQt6.QtWidgets import QFileDialog
        from kvm import generate_mac_client, local_ip

        desktop = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DesktopLocation)
        default_path = (Path(desktop) if desktop else Path.home()) / "Airflow-Mac-Client.command"
        path, _ = QFileDialog.getSaveFileName(
            self, "保存 Mac 端一键脚本", str(default_path),
            "Shell 脚本 (*.command)")
        if not path:
            return
        ok, msg = generate_mac_client(Path(path))
        if ok:
            QMessageBox.information(
                self, "已生成 Mac 端脚本",
                f"已生成：\n{msg}\n\n本机局域网 IP：{local_ip()}\n\n"
                "把这个文件拷到 Mac 上，双击运行即可（首次会自动下载安装 Deskflow）。\n"
                "如果双击提示没有权限：右键 → 打开，或在终端执行 chmod +x 该文件。")
        else:
            QMessageBox.warning(self, "生成失败", msg)

    def _reset_defaults(self) -> None:
        d = Settings()
        self.size_combo.setCurrentIndex(self.size_combo.findData(d.video_size))
        self.quality_combo.setCurrentIndex(self.quality_combo.findData(d.video_quality))
        self.fps_combo.setCurrentIndex(self.fps_combo.findData(d.fps))
        self.audio_check.setChecked(d.audio_enabled)
        self.flip_combo.setCurrentIndex(self.flip_combo.findData(d.flip_mode))
        self.rotate_combo.setCurrentIndex(self.rotate_combo.findData(d.rotate_mode))
        self.mode_combo.setCurrentIndex(self.mode_combo.findData(d.display_mode))
        self.monitor_combo.setCurrentIndex(self.monitor_combo.findData(0))
        self.top_check.setChecked(d.always_on_top)
        self.remember_check.setChecked(d.remember_window)
        self.standalone_check.setChecked(d.standalone)
        self.cursor_check.setChecked(d.hide_cursor)
        self.overlay_check.setChecked(d.status_overlay)
        self.ipad_mode_combo.setCurrentIndex(self.ipad_mode_combo.findData(d.ipad_mode))
        self.mac_mode_combo.setCurrentIndex(self.mac_mode_combo.findData(d.mac_mode))
        self.ask_check.setChecked(d.ask_on_connect)
        self.name_edit.setText(d.device_name)
        self.autostart_check.setChecked(d.auto_start)
        self.sleep_check.setChecked(d.prevent_sleep)
        self.tray_check.setChecked(d.tray_enabled)
        self.minimize_check.setChecked(d.minimize_to_tray)
        self.sound_check.setChecked(d.connect_sound)
        self.kvm_check.setChecked(d.kvm_enabled)
        self.lan_check.setChecked(d.lan_share)

    def result_settings(self) -> Settings:
        """读取对话框当前值（供保存/应用）。"""
        s = Settings()
        s.device_name = self.name_edit.text().strip() or "iPad-Screen"
        s.video_size = self.size_combo.currentData()
        s.video_quality = self.quality_combo.currentData()
        s.fps = self.fps_combo.currentData()
        s.audio_enabled = self.audio_check.isChecked()
        s.flip_mode = self.flip_combo.currentData()
        s.rotate_mode = self.rotate_combo.currentData()
        s.display_mode = self.mode_combo.currentData()
        s.monitor_index = self.monitor_combo.currentData() or 0
        s.always_on_top = self.top_check.isChecked()
        s.remember_window = self.remember_check.isChecked()
        s.standalone = self.standalone_check.isChecked()
        s.hide_cursor = self.cursor_check.isChecked()
        s.status_overlay = self.overlay_check.isChecked()
        s.ipad_mode = self.ipad_mode_combo.currentData()
        s.mac_mode = self.mac_mode_combo.currentData()
        s.ask_on_connect = self.ask_check.isChecked()
        s.auto_start = self.autostart_check.isChecked()
        s.prevent_sleep = self.sleep_check.isChecked()
        s.tray_enabled = self.tray_check.isChecked()
        s.minimize_to_tray = self.minimize_check.isChecked()
        s.connect_sound = self.sound_check.isChecked()
        s.kvm_enabled = self.kvm_check.isChecked()
        s.deskflow_path = self._deskflow_path
        s.lan_share = self.lan_check.isChecked()
        return s