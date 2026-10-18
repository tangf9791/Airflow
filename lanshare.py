# -*- coding: utf-8 -*-
"""局域网分享：把 Mac 客户端脚本通过 HTTP 提供给同网段的 Mac 下载。"""

from __future__ import annotations

import html
import io
import threading
import time
import zipfile
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
  body { margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
    background: radial-gradient(1200px 600px at 20% 0%, #1b2a4a 0%, #0d0f14 60%);
    color: #e8e8ec; font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; padding: 28px; }
  .card { width: min(640px, 100%); background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.09);
    border-radius: 18px; padding: 30px; }
  h1 { margin: 0 0 4px; font-size: 26px; }
  .sub { margin: 0 0 24px; color: #9aa3b2; font-size: 14px; }
  .big { display: block; width: 100%; text-align: center; text-decoration: none; padding: 16px 18px;
    border-radius: 12px; border: none; cursor: pointer; font-size: 17px; font-weight: 700;
    background: linear-gradient(135deg, #38bdf8, #7c3aed); color: #fff; margin: 8px 0; }
  .big.alt { background: #1e293b; border: 1px solid #3b4a63; color: #dbeafe; font-weight: 600; font-size: 16px; }
  .big:active { transform: translateY(1px); }
  .step { color: #9aa3b2; font-size: 13px; line-height: 1.75; margin: 8px 0 0; }
  .cmd { margin: 10px 0 4px; padding: 13px 15px; border-radius: 10px; background: #0a0d13; border: 1px solid #2a3444;
    font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 12.5px; color: #7dd3fc;
    white-space: pre-wrap; word-break: break-all; user-select: text; -webkit-user-select: text; }
  .ok { color: #34d399; font-size: 13px; display: none; margin-top: 6px; }
  .note { margin-top: 14px; color: #f0a04b; font-size: 12px; line-height: 1.7; }
  .meta { margin-top: 22px; color: #6f7889; font-size: 12px; }
  h2 { margin: 22px 0 4px; font-size: 15px; color: #c9d1e0; }
</style>
</head>
<body>
  <div class="card">
    <h1>Airflow</h1>
    <p class="sub">Mac 键盘共享客户端 · 自动匹配这台 Windows 电脑</p>

    <h2>方式一：下载后双击（推荐）</h2>
    <a class="big" href="/client.zip">下载 Mac 客户端（.zip）</a>
    <p class="step">解压后双击 <b>Airflow-Mac-Client.command</b>。
    如果提示“未验证的开发者”，右键点它 → 打开 → 再点“打开”即可（只需一次）。</p>

    <h2>方式二：终端一行命令</h2>
    <div class="cmd" id="cmd">curl -fsSL http://{{IP}}:{{PORT}}/install.sh | bash</div>
    <button class="big alt" onclick="copyCmd()">复制命令</button>
    <span class="ok" id="ok">已复制，去 Mac 终端粘贴回车即可</span>

    <p class="note">首次运行会自动下载安装 Deskflow（需联网）。之后在
    「系统设置 → 隐私与安全性 → 辅助功能」勾选 Deskflow。
    退出：按 Ctrl+C，会有提示音和通知。</p>
    <p class="meta">Windows 端：{{IP}}:{{PORT}} · 仅限本局域网访问</p>
  </div>
  <script>
    function copyCmd() {
      var t = document.getElementById('cmd').innerText;
      function done() { var ok = document.getElementById('ok'); ok.style.display = 'inline';
        setTimeout(function () { ok.style.display = 'none'; }, 2500); }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(t).then(done, fallback);
      } else { fallback(); }
      function fallback() {
        var r = document.createRange(); r.selectNode(document.getElementById('cmd'));
        var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r);
        try { document.execCommand('copy'); done(); } catch (e) {}
      }
    }
  </script>
</body>
</html>
"""


def build_client_zip() -> bytes | None:
    """把 .command 打包成 zip，并写入 Unix 执行权限（解压后可直接双击）。"""
    text = kvm.mac_client_text()
    if text is None:
        return None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        info = zipfile.ZipInfo("Airflow-Mac-Client.command")
        info.create_system = 3          # Unix：让 macOS 保留权限
        info.external_attr = 0o100755 << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        info.date_time = time.localtime()[:6]
        zf.writestr(info, text.encode("utf-8"))
    return buf.getvalue()


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

    def _send_install(self) -> None:
        text = kvm.mac_install_text()
        if text is None:
            self.send_error(500, "install template unavailable")
            return
        data = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_zip(self) -> None:
        data = build_client_zip()
        if data is None:
            self.send_error(500, "client template unavailable")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition",
                         'attachment; filename="Airflow-Mac-Client.zip"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/client.zip", "/app.zip", "/Airflow-Mac-Client.zip"):
            self._send_zip()
        elif path in ("/install.sh", "/install"):
            self._send_install()
        elif path in ("/", "/index.html"):
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