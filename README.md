# Airflow（iPad 投屏接收端）

![Airflow](app_icon.png)

一个极简的 Windows AirPlay 镜像接收桌面程序：用 **PyQt6** 做无边框、置顶、
全屏的管理界面，在后台拉起开源 **uxplay.exe** 接收 iPad / Mac 投屏，并把视频窗口
内嵌到本程序自己的窗口里显示。

## 下载使用（推荐）

1. 打开 [Releases](https://github.com/tangf9791/Airflow/releases) 下载最新的 `Airflow.exe`（单文件，**无需安装 Python、无需编译、无需任何依赖**，下载即用；已内置 uxplay 运行环境）；
2. 如果电脑没装过 Bonjour，先装 [Bonjour Print Services](https://support.apple.com/downloads/bonjour-print-services-for-windows)
   （或运行 `uxplay/1-安装Bonjour.bat`）；
3. 双击运行，在 iPad / Mac 上打开“屏幕镜像”，选择 **iPad-Screen** 即可。

> 首次启动需要解压内置运行环境（约 5~10 秒），之后每次启动略慢于普通小工具，属正常现象。
> 按 **F1** 打开设置，**F5** 重启投屏服务，**ESC / Q** 退出。

- 按 **ESC** 或 **Q**（全局热键，任何窗口聚焦时都有效）→ 立即安全终止 uxplay 并退出
- 按 **F1** → 打开设置面板：视频尺寸 / 画质 / 帧率、全屏 / 窗口模式、设备名、开机自启
- 按 **Alt+F4** 关闭窗口 → 同样会先清理后台 uxplay 进程再退出
- 退出时先向 uxplay 发送 WM_CLOSE 优雅关闭，超时再强制结束，确保不留后台进程
- 投屏期间自动禁止熄屏/系统休眠（可在设置中关闭）
- 托盘图标常驻（可关）、状态角标、全屏闲置自动隐藏鼠标指针
- 按 **F5** 一键重启投屏服务（改设置后自动重启；也可在托盘菜单操作）
- 音频开关、画面翻转/旋转、多显示器选择、窗口位置记忆、连接提示音
- 按客户端类型自动呈现：iPad 投屏默认全屏拉伸，Mac 连接默认 1:1 扩展（像第二块显示器），
  也可在连接时弹窗快速选择，或按 **F2** 随时切换
- 设置自动保存到 `%APPDATA%\Airflow\config.json`

## 目录结构

| 文件 | 说明 |
| --- | --- |
| `main.py` | 程序主体（唯一的源码文件） |
| `Airflow.spec` | PyInstaller 单文件打包配置 |
| `build.bat` | 一键打包脚本 |
| `download_uxplay.ps1` | 下载预编译 uxplay 到 `uxplay\` 子目录的脚本 |
| `requirements.txt` / `requirements-build.txt` | 运行 / 构建依赖 |

## 环境依赖

1. **Python 3.9+**（开发运行用；打包出的 exe 不需要 Python）。
2. **uxplay.exe**（开源，任选一种方式获取；**使用打包好的 exe 则无需准备**，已内置）：
   - **方式 A（推荐，官方 SDL 版）**：从 [FDH2/UxPlay](https://github.com/FDH2/UxPlay)
     源码用 MSYS2 编译，得到 `uxplay.exe`（支持 `-fs`、`-fps`、`-vsync no` 等参数）。
   - **方式 B（预编译，最快）**：运行 `download_uxplay.ps1`，从
     [leapbtw/uxplay-windows](https://github.com/leapbtw/uxplay-windows/releases)
     下载 GStreamer 版预编译包并放到 `uxplay\` 子目录（此包自带
     `mDNSResponder.exe`，可替代 Apple Bonjour）。
   - 程序会按以下顺序查找 `uxplay.exe`：
     `UXPLAY_EXE` 环境变量 → 程序同目录 → 同目录 `uxplay\` 子目录 → 当前目录 → PATH。
3. **Apple Bonjour 服务**：方式 B 的 uxplay 1.73.6 依赖 Bonjour。安装
   [Bonjour Print Services for Windows](https://support.apple.com/downloads/bonjour-print-services-for-windows)
   或运行包内 `1-安装Bonjour.bat`，并确认“Bonjour Service”（mDNSResponder.exe）
   正在运行。方式 A 的 UxPlay ≥ 1.74 自带 mDNS，无需另装 Bonjour。
4. **Windows 防火墙**：放行 uxplay.exe 的入站连接（AirPlay 默认端口 5000、7000 等）。

## 运行（源码方式）

```bat
python -m pip install -r requirements.txt
python main.py
```

启动后屏幕进入全屏黑底界面，显示“等待 iPad 投屏连接…”，然后在 iPad 控制中心
打开“屏幕镜像”，选择 **iPad-Screen** 即可。

常用参数：

| 参数 | 作用 |
| --- | --- |
| `--standalone` | 不内嵌视频，改用 uxplay 自带全屏窗口（等价于 `uxplay -n "iPad-Screen" -fs -fps 60 -vsync no`） |
| `--no-uxplay` | 不启动 uxplay（只测试窗口与热键） |
| `--smoke N` | N 秒后自动退出（自动化测试用） |
| `--screenshot a.png` | 启动约 2 秒后保存整屏截图（调试用） |

## 打包为单文件 exe

```bat
build.bat
```

或者手动执行：

```bat
python -m pip install -r requirements-build.txt
pyinstaller --clean --noconfirm Airflow.spec
```

产物：`dist\Airflow.exe`（单文件，约 240 MB，无控制台窗口，已内置 uxplay 运行环境）。
把 `uxplay.exe` 放到该 exe 同目录（或 `dist\uxplay` 子目录）即可分发使用。

> 说明：PyQt6 的钩子已内置于 PyInstaller；spec 中显式列出了 Qt 模块的
> hiddenimports 作为保险。若在别的机器上运行报“缺 DLL”，安装
> [Microsoft Visual C++ Redistributable](https://learn.microsoft.com/zh-cn/cpp/windows/latest-supported-vc-redist)。

## 设置面板（F1）

按 **F1** 随时打开设置面板（投屏过程中也可用），修改后点“保存并应用”立即生效
（视频相关设置会重启一次 uxplay 服务）：

| 标签页 | 选项 | 说明 |
| --- | --- | --- |
| 视频 | 视频尺寸 | 原机/自动（不指定）、720p、1080p、1440p、4K（4K 需配合高画质） |
| 视频 | 视频画质 | 标准（H.264）/ 高（H.265，支持 4K） |
| 视频 | 帧率 | 原机（不指定，默认 30）、60、90、120 |
| 视频 | 传输音频 | 声音同步到本机（关闭时 uxplay 加 `-as 0`） |
| 视频 | 翻转 / 旋转 | 水平、垂直、180° 倒置 / 顺时针、逆时针 90°（`-f` / `-r`） |
| 显示 | 显示模式 | 全屏（默认，无边框置顶）/ 窗口（可调整大小） |
| 显示 | 显示器 | 多显示器时全屏用哪块屏 |
| 显示 | 窗口总在最前 | 窗口模式下是否置顶 |
| 显示 | 记住窗口位置大小 | 窗口模式下次启动恢复上次位置 |
| 显示 | 独立模式 | 使用 uxplay 自带全屏窗口（`-fs`），本程序仅负责热键与清理 |
| 显示 | 隐藏鼠标指针 | 全屏闲置 2 秒自动隐藏，动一下鼠标恢复 |
| 显示 | 状态角标 | 右上角显示设备名 / 分辨率 / 帧率 / 连接状态 / 投屏时长 |
| 显示 | iPad 显示方式 | iPad 连接时全屏拉伸 / 1:1 扩展 |
| 显示 | Mac 显示方式 | Mac 连接时全屏拉伸 / 1:1 扩展（默认 1:1） |
| 显示 | 连接时快速选择 | 客户端连上时弹窗选择本次的显示方式（默认关） |
| 常规 | 设备名称 | iPad 屏幕镜像里显示的名字（`-n`） |
| 常规 | 开机自启动 | 写入 HKCU Run 注册表，登录时自动启动 |
| 常规 | 禁止自动熄屏/休眠 | 投屏期间阻止屏幕自动熄灭与系统睡眠（默认开启，退出自动释放） |
| 常规 | 托盘图标 | 托盘常驻，菜单含 显示窗口 / 设置 / 重启服务 / 退出 |
| 常规 | 关闭时最小化到托盘 | 开启后 Alt+F4 隐藏到托盘而不退出（默认关闭） |
| 常规 | 连接提示音 | 客户端连上时播放系统提示音 |

设置文件：`%APPDATA%\Airflow\config.json`（手动编辑亦可，重启程序生效）。

## 配置（环境变量）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `UXPLAY_EXE` | （自动查找） | uxplay.exe 的完整路径 |
| `UXPLAY_NAME` | `iPad-Screen` | AirPlay 设备名（iPad 上显示的名字） |
| `UXPLAY_FPS` | `60` | 最大帧率 |
| `UXPLAY_VSYNC` | `no` | 关闭音视频时间戳同步，适合直播场景 |
| `UXPLAY_ARGS` | （空） | 完全自定义 uxplay 参数（覆盖默认，空格分隔） |
| `UXPLAY_EMBED` | `1` | 设为 `0` 等同 `--standalone` |

示例：`set UXPLAY_NAME=My-iPad` 后启动，iPad 上会看到名为“My-iPad”的设备。

## 镜像 vs 扩展屏（Mac）

**"镜像 / 扩展"由 Mac 端决定**：Mac 的 AirPlay 菜单里可选「镜像内置显示器」或
「用作单独的显示器」（后者就是扩展屏）。AirPlay 协议里这是发送端的选择，接收端
（PC）无法替 Mac 改选。

PC 端能控制的是**收到画面后怎么呈现**，在 设置 → 显示 里：

- **全屏拉伸**：铺满整块屏幕（iPad 镜像的默认观感）；
- **1:1 扩展**：按 iPad/Mac 送来的原始分辨率居中显示、不拉伸，超出屏幕时等比缩小——
  接近"多了一块显示器"的效果，也顺带解决了两端都是 4K 时画面比例不对的问题
  （Mac 端建议把 AirPlay 显示器的分辨率设成 1080p，PC 端 1:1 显示即清晰且尺寸正常）。

默认策略：iPad → 全屏拉伸，Mac → 1:1 扩展。想临时换：按 **F2** 或托盘菜单
"显示方式"，也可以在设置里勾选"连接时弹出快速选择窗口"。

## 与 Mac / 另一台电脑联动（键盘共享）

AirPlay 镜像协议是**单向**的：视频/音频从发送端流到接收端，协议里没有鼠标/键盘回传通道
（播放控制用的 DACP 通道也只管上一曲/播放/暂停）。所以"用 PC 键盘控制 MacBook"需要走
另一条链路，成熟做法是跨平台 KVM 软件：

- 推荐 [Deskflow](https://deskflow.org)（开源，Windows ↔ macOS，局域网内键盘+鼠标共享，
  把 Mac 配成客户端；用屏幕边缘或热键切换键盘焦点）。
- 使用 AirPlay 镜像时，Mac 的画面已经显示在 PC 上，Deskflow 的"切换到 Mac 屏幕"正好对着
  镜像窗口操作，体验很顺。

> 蓝牙方案（让 PC 伪装成蓝牙键盘）在 Windows 上不可行：没有 HID 设备角色的公开 API，
> 实验性 BLE HOGP 方案存在随机蓝牙地址、重启后需重新配对等已知问题。

## 常见问题

- **找不到 uxplay.exe**：源码运行时按“环境依赖”第 2 条放置；打包版已内置，若仍提示
  找不到，说明 exe 被安全软件拦截了解压（PyInstaller 单文件机制），可把 uxplay 放到
  exe 同目录的 `uxplay` 子目录绕过。
- **uxplay 启动后立刻退出（代码非 0）**：多半是 Bonjour/mDNS 未就绪或参数不受支持；
  可查看日志 `%TEMP%\Airflow.log` 中的 `uxplay: ...` 输出定位原因。
- **内嵌后黑屏 / 花屏**：视频窗口重挂载失败，改用 `--standalone` 模式（uxplay 自带全屏窗口）。
- **iPad 搜不到设备**：确认 PC 与 iPad 同一局域网、防火墙已放行 uxplay，
  以及 Bonjour Service（或 uxplay 自带的 mDNSResponder）正在运行。
- **日志位置**：`%TEMP%\Airflow.log`，退出前会自动记录 uxplay 的清理过程。

## 第三方组件与许可

- 本项目代码采用 [MIT 许可证](LICENSE)；
- 接收引擎为开源项目 [UxPlay](https://github.com/FDH2/UxPlay)（GPL-3.0），本项目通过
  命令行驱动它、不修改其源码；单文件发布版内置的是其 Windows 预编译包
  （[yztshh/Uxplay-airplay](https://github.com/yztshh/Uxplay-airplay/releases)）。
  如需获取 UxPlay 源码，请访问上述仓库；
- 图标为本项目自制。