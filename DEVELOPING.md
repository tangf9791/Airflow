# 开发与构建

面向想从源码运行或自行打包的开发者。普通用户请直接下载 [Releases](https://github.com/tangf9791/Airflow/releases) 里的 exe。

## 环境

- Windows 10/11 x64，Python 3.9+
- [PyQt6](https://pypi.org/project/PyQt6/)、[PyInstaller](https://pyinstaller.org/)
- uxplay 运行环境（Windows 预编译包）：
  - 自动：运行 `download_uxplay.ps1`
  - 手动：从 [yztshh/Uxplay-airplay releases](https://github.com/yztshh/Uxplay-airplay/releases)
    下载 `UxPlay-Windows-1.73.6-final.zip`，解压到本目录的 `uxplay\` 子目录
- Apple Bonjour（首次运行 exe 会自动安装；源码运行可手动运行 `uxplay\1-安装Bonjour.bat`）

## 从源码运行

```bat
python -m pip install -r requirements.txt
python main.py
```

## 打包为单文件 exe

```bat
python -m pip install -r requirements-build.txt
pyinstaller --clean --noconfirm Airflow.spec
```

产物为 `dist\Airflow.exe`（内置 uxplay、Deskflow 便携包与图标，约 260 MB）。

## 项目结构

| 文件 | 说明 |
| --- | --- |
| `main.py` | 窗口、热键、uxplay / Deskflow 生命周期、Bonjour 自动安装 |
| `config.py` | 设置定义、持久化、开机自启注册表 |
| `settings_dialog.py` | 设置面板（视频 / 显示 / 键盘共享 / 常规） |
| `kvm.py` | Deskflow 集成辅助（查找 / 解压 / 检测） |
| `Airflow.spec` | PyInstaller 打包配置 |
| `app_icon.ico` / `app_icon.png` | 图标 |
| `deskflow-portable.zip` | 内置 Deskflow 便携包（MIT 项目 GPL-3.0，发布时一并提供源码链接） |

## 配置

设置保存在 `%APPDATA%\Airflow\config.json`（旧版 iPadScreenReceiver / AirMirror 的配置会自动迁移）。

常用环境变量（临时覆盖，调试用）：

| 变量 | 说明 |
| --- | --- |
| `UXPLAY_EXE` | uxplay.exe 完整路径 |
| `UXPLAY_ARGS` | 完全自定义 uxplay 参数 |
| `UXPLAY_EMBED` | `0` = 独立模式（uxplay 自带全屏窗口） |

## 测试开关

```bat
python main.py --smoke 6        # 6 秒后自动退出
python main.py --no-uxplay      # 不启动投屏服务
python main.py --screenshot a.png  # 启动 2 秒后截图
python main.py --standalone     # uxplay 自带全屏窗口模式
```
