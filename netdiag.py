# -*- coding: utf-8 -*-
"""网络诊断：检查 AirPlay 接收的关键条件（IP / Bonjour / 防火墙 / 进程）。"""

from __future__ import annotations

import socket
import subprocess


def _run(cmd: list[str], timeout: int = 12) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError) as exc:
        return -1, str(exc)


def local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("223.5.5.5", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return ""


def diagnose() -> str:
    lines: list[str] = []
    ip = local_ip()
    lines.append(f"本机局域网 IP：{ip or '未获取到（检查网络）'}")

    code, out = _run(["sc", "query", "Bonjour Service"])
    if code != 0:
        lines.append("Bonjour 服务：未安装（启动 Airflow 时会自动安装）")
    elif "RUNNING" in out.upper():
        lines.append("Bonjour 服务：运行中 ✓")
    else:
        lines.append("Bonjour 服务：已安装但未运行（重启 Airflow 会自动拉起）")

    code, out = _run(["netsh", "advfirewall", "firewall", "show", "rule", "name=Airflow uxplay"])
    if code == 0 and "allow" in out.lower():
        lines.append("uxplay 防火墙放行：已配置 ✓")
    else:
        lines.append("uxplay 防火墙放行：缺失（重启 Airflow 会自动添加，需点一次 UAC）")

    code, out = _run(["powershell", "-NoProfile", "-Command",
                      "(Get-NetConnectionProfile | Select-Object -First 1).NetworkCategory"],
                     timeout=25)
    cat = out.strip().splitlines()[-1].strip() if out.strip() else "未知"
    lines.append(f"网络类型：{cat}" + (" ✓" if cat.lower() == "private" else "（建议改为“专用网络”）"))

    code, out = _run(["tasklist", "/FI", "IMAGENAME eq uxplay.exe"])
    lines.append("uxplay 进程：" + ("运行中 ✓" if "uxplay.exe" in out.lower() else "未运行"))

    code, out = _run(["tasklist", "/FI", "IMAGENAME eq deskflow.exe"])
    lines.append("Deskflow 进程：" + ("运行中 ✓" if "deskflow.exe" in out.lower() else "未运行"))
    return "\n".join(lines)
