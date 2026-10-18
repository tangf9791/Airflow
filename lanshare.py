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
  .card { width: min(620px, 100%); background: rgba(255,255,255,.04);
          border: 1px solid rgba(255,255,255,.09); border-radius: 18px; padding: 32px; }
  h1 { margin: 0 0 4px; font-size: 26px; letter-spacing: .5px; }
  .sub { margin: 0 0 26px; color: #9aa3b2; font-size: 14px; }
  h2 { margin: 26px 0 8px; font-size: 15px; color: #c9d1e0; display: flex; align-items: center; gap: 8px; }
  .rec { font-size: 12px; color: #34d399; border: 1px solid #34d39955; border-radius: 999px; padding: 2px 10px; }
  .step { color: #9aa3b2; font-size: 13px; line-height: 1.7; margin: 6px 0; }
  .cmd {
    margin: 10px 0 6px; padding: 14px 16px; border-radius: 10px; background: #0a0d13;
    border: 1px solid #2a3444; font-family: "SF Mono", Menlo, Consolas, monospace;
    font-size: 13px; color: #7dd3fc; white-space: pre-wrap; word-break: break-all;
    user-select: text; -webkit-user-select: text;
  }
  .row { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
  .btn { display: inline-block; text-align: center; text-decoration: none; padding: 12px 18px;
         border-radius: 10px; border: none; cursor: pointer; font-size: 15px; font-weight: 600;
         background: linear-gradient(135deg, #38bdf8, #7c3aed); color: #fff; }
  .btn.ghost { background: transparent; border: 1px solid #3b4a63; color: #c9d1e0;
               font-weight: 500; font-size: 14px; padding: 10px 16px; }
  .ok { color: #34d399; font-size: 13px; display: none; }
  .note { margin-top: 10px; color: #f0a04b; font-size: 12px; line-height: 1.7; }
  .meta { margin-top: 26px; color: #6f7889; font-size: 12px; }
  code { background: #0a0d13; border: 1px solid #2a3444; border-radius: 4px; padding: 1px 5px; }
</style>
</head>
<body>
  <div class="card">
    <h1>Airflow</h1>
    <p class="sub">Mac 键盘共享客户端 · 局域网直发</p>

    <h2>方式一：终端里粘贴一行命令 <span class="rec">推荐</span></h2>
    <p class="step">在 Mac 打开「终端」（Terminal），粘贴下面这行，回车即可。无需下载文件、不涉及文件权限。</p>
    <div class="cmd" id="cmd">curl -fsSL http://{{IP}}:{{PORT}}/install.sh | bash</div>
    <div class="row">
      <button class="btn" onclick="copyCmd()">复制命令</button>
      <span class="ok" id="ok">已复制，去 Mac 终端粘贴即可</span>
    </div>

    <h2>方式二：下载脚本文件</h2>
    <p class="step">下载后双击运行。<b>若提示“没有权限执行”</b>，请在终端执行：</p>
    <div class="cmd">chmod +x ~/Downloads/Airflow-Mac-Client.command</div>
    <div class="row">
      <a class="btn ghost" href="/download">下载 Airflow-Mac-Client.command</a>
    </div>

    <h2>之后</h2>
    <p class="step">首次运行会自动下载安装 Deskflow（需联网，装到 /Applications）。
    然后在「系统设置 → 隐私与安全性 → 辅助功能」里勾选 Deskflow。
    退出时按 <code>Ctrl+C</code>，会播放提示音并通知。</p>

    <p class="meta">Windows 端：{{IP}}:{{PORT}} · 仅限本局域网访问</p>
  </div>
  <script>
    function copyCmd() {
      var t = document.getElementById('cmd').innerText;
      function done() {
        var ok = document.getElementById('ok');
        ok.style.display = 'inline';
        setTimeout(function () { ok.style.display = 'none'; }, 2500);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(t).then(done, fallback);
      } else { fallback(); }
      function fallback() {
        var r = document.createRange();
        r.selectNode(document.getElementById('cmd'));
        var sel = window.getSelection();
        sel.removeAllRanges(); sel.addRange(r);
        try { document.execCommand('copy'); done(); } catch (e) {}
      }
    }
  </script>
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

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/install.sh", "/install"):
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