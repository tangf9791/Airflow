# -*- coding: utf-8 -*-
"""局域网分享：把 Mac 客户端脚本通过 HTTP 提供给同网段的 Mac 下载。"""

from __future__ import annotations

import html
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import kvm

_DEFAULT_PORT = 8123
_MAX_TRIES = 20

_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Airflow · Mac 客户端</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
    background: radial-gradient(1200px 600px at 20% 0%, #1b2a4a 0%, #0d0f14 60%);
    color: #e8e8ec; font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    padding: 32px;
  }
  .card { width: min(560px, 100%); background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.09);
          border-radius: 18px; padding: 32px; backdrop-filter: blur(8px); }
  h1 { margin: 0 0 4px; font-size: 26px; letter-spacing: .5px; }
  .sub { margin: 0 0 24px; color: #9aa3b2; font-size: 14px; }
  .btn { display: block; text-align: center; text-decoration: none; padding: 14px 18px; border-radius: 12px;
         background: linear-gradient(135deg, #38bdf8, #7c3aed); color: #fff; font-size: 16px; font-weight: 600;
         box-shadow: 0 6px 24px rgba(56,189,248,.25); }
  .btn:active { transform: translateY(1px); }
  h2 { margin: 28px 0 10px; font-size: 15px; color: #c9d1e0; }
  ol { margin: 0; padding-left: 20px; color: #b9c1cf; font-size: 14px; line-height: 1.8; }
  .meta { margin-top: 24px; color: #6f7889; font-size: 12px; }
  .tag { display: inline-block; margin-top: 10px; padding: 3px 10px; border-radius: 999px;
         background: rgba(56,189,248,.12); color: #7dd3fc; font-size: 12px; }
</style>
</head>
<body>
  <div class="card">
    <h1>Airflow</h1>
    <p class="sub">Mac 键盘共享客户端 · 局域网直发</p>
    <a class="btn" href="/download">下载 Mac 客户端（.command）</a>
    <span class="tag">已自动填入本机 IP：{{IP}}</span>
    <h2>使用方法</h2>
    <ol>
      <li>下载后双击运行；若提示权限，右键 → 打开，或在终端执行 <b>chmod +x</b>。</li>
      <li>首次运行会自动下载安装 Deskflow（需要联网）。</li>
      <li>在 Mac「系统设置 → 隐私与安全性 → 辅助功能」里勾选 Deskflow。</li>
      <li>回到 Windows 的 Deskflow 界面，把 Mac 加为右侧屏幕，鼠标移到屏幕右边缘即可切换。</li>
    </ol>
    <p class="meta">Windows 端：{{IP}}:{{PORT}} · 仅限本局域网访问</p>
  </div>
</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    server_version = "AirflowLanShare/1.0"

    def log_message(self, fmt, *args):  # 静默访问日志，避免刷屏
        pass

    def _send_html(self, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_client(self) -> None:
        text = kvm.mac_client_text()
        if text is None:
            self.send_error(500, "client template unavailable")
            return
        data = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition",
                         'attachment; filename="Airflow-Mac-Client.command"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            ip = html.escape(kvm.local_ip() or "127.0.0.1")
            body = (_PAGE.replace("{{IP}}", ip)
                         .replace("{{PORT}}", str(getattr(self.server, "airflow_port", 0))))
            self._send_html(body)
        elif path in ("/download", "/Airflow-Mac-Client.command"):
            self._send_client()
        else:
            self.send_error(404, "not found")


class LanShare:
    """局域网分享服务（只读，仅提供页面与客户端脚本）。"""

    def __init__(self):
        self._httpd = None
        self._thread = None
        self.port = 0

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def url(self) -> str:
        return f"http://{kvm.local_ip()}:{self.port}/"

    def start(self, port: int = _DEFAULT_PORT) -> tuple[bool, str]:
        if self._httpd is not None:
            return True, self.url()
        if kvm.local_ip() == "":
            return False, "无法获取本机局域网 IP"
        if kvm.mac_client_text() is None:
            return False, "未找到 Mac 客户端模板（安装包不完整）"
        for p in range(port, port + _MAX_TRIES):
            try:
                httpd = ThreadingHTTPServer(("0.0.0.0", p), _Handler)
            except OSError:
                continue
            httpd.daemon_threads = True
            httpd.airflow_port = p
            self._httpd = httpd
            self.port = p
            self._thread = threading.Thread(
                target=httpd.serve_forever, daemon=True, name="airflow-lan-share")
            self._thread.start()
            return True, self.url()
        return False, "没有可用端口（8123 起已被占用）"

    def stop(self) -> None:
        httpd = self._httpd
        self._httpd = None
        self._thread = None
        if httpd is not None:
            try:
                httpd.shutdown()
                httpd.server_close()
            except OSError:
                pass
