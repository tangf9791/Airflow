# Airflow — AirPlay 镜像接收器（Windows）

![Airflow](app_icon.png)

把 iPad / Mac 的屏幕无线投到 Windows 电脑上，画面清晰、延迟低。单文件运行，下载即用。

## 下载使用（三步）

1. 打开 [Releases](https://github.com/tangf9791/Airflow/releases) 下载 `Airflow.exe`；
2. 双击运行（首次启动会自动安装 Apple Bonjour，如弹出「用户账户控制」请点「是」）；
3. 在 iPad / Mac 上打开「屏幕镜像」，选择 **iPad-Screen**。

**不需要安装 Python，不需要编译，不需要手动装任何依赖。**

## 功能

- 无边框置顶全屏，画面直接铺满屏幕
- 按设备自动区分：iPad 投屏走「全屏镜像」，Mac 走「扩展屏（1:1 不拉伸）」，按 **F2** 可随时切换
- 视频尺寸 / 画质（H.265 4K）/ 帧率 / 音频开关 / 画面翻转旋转
- 多显示器选择、窗口位置记忆、托盘图标
- 投屏状态角标（设备名、分辨率、帧率、连接时长）
- 全屏闲置自动隐藏鼠标指针
- 投屏期间禁止自动熄屏 / 系统休眠
- 开机自启、设备名自定义、连接提示音

## 快捷键

| 按键 | 作用 |
| --- | --- |
| **F1** | 打开设置面板 |
| **F5** | 重启投屏服务 |
| **F2** | 切换显示方式（全屏镜像 ↔ 扩展屏） |
| **ESC / Q** | 退出（会先安全关闭投屏服务） |

## 设置面板（F1）

| 页签 | 内容 |
| --- | --- |
| 视频 | 尺寸、画质、帧率、音频开关、翻转、旋转 |
| 显示 | 全屏 / 窗口、显示器选择、置顶、记忆窗口、独立模式、隐藏鼠标、状态角标 |
| 键盘共享 | 见下节 |
| 常规 | 设备名、开机自启、禁止熄屏、托盘、关闭到托盘、连接提示音 |

## 键盘共享（KVM，Deskflow）

本程序内置了开源 KVM 工具 [Deskflow](https://github.com/deskflow/deskflow)，可以让一套
键盘鼠标同时控制 PC 和 Mac（**注意：AirPlay 协议本身不传键盘鼠标，这是独立的一条通道**）。

1. 设置 → 键盘共享 → 勾选「启用键盘共享」；
2. 点「打开 Deskflow 界面」，本机模式选 **Server**，把 Mac 添加为一台屏幕（放在本机右侧）；
3. Mac 上安装 Deskflow 客户端（[下载](https://github.com/deskflow/deskflow/releases)），
   填本机局域网 IP、端口 **24800**，连接；
4. 之后鼠标移到屏幕右边缘，键盘就切换到了 Mac；按 **Scroll Lock** 可锁定在当前电脑。

> Mac 端首次使用需在「系统设置 → 隐私与安全性 → 辅助功能」里勾选 Deskflow。

### 局域网直发（Mac 一键连接）

设置 → 键盘共享 → 勾选「启用键盘共享」和「局域网分享」并保存后，主界面会**大字显示网址**；
点「复制下载链接」按钮或按 **F3** 即可复制（托盘菜单里也有）：

```
http://<本机IP>:8123/
```

Mac 上两种方式（推荐方式一，不涉及文件权限）：

**方式一（推荐）**：打开「终端」，粘贴这一行回车：

```sh
curl -fsSL http://<本机IP>:8123/install.sh | bash
```

**方式二**：浏览器打开上面的网址，下载 `Airflow-Mac-Client.command` 双击运行；
若提示"没有权限执行"，在终端执行 `chmod +x ~/Downloads/Airflow-Mac-Client.command`。

两种方式都会自动安装 Deskflow、写入配置并启动客户端；按 `Ctrl+C` 退出（有提示音和通知）。


## 常见问题

- **iPad / Mac 搜不到设备**：确认同一局域网、防火墙已放行 uxplay；首次运行时允许 Bonjour 自动安装。
- **画面比例不对**：在设置 → 显示里切换「全屏镜像 / 扩展屏」，或在 Mac 端把扩展屏分辨率调成 1080p。
- **想改分辨率/帧率**：设置 → 视频，改完会自动重启投屏服务。
- **日志**：`%TEMP%\Airflow.log`。

## 许可与致谢

- 本项目代码：[MIT](LICENSE)
- 接收引擎：[UxPlay](https://github.com/FDH2/UxPlay)（GPL-3.0），Windows 预编译包来自
  [yztshh/Uxplay-airplay](https://github.com/yztshh/Uxplay-airplay/releases)
- 键盘共享：[Deskflow](https://github.com/deskflow/deskflow)（GPL-3.0）
- 图标：本项目自制

源码结构、构建与打包说明见 [DEVELOPING.md](DEVELOPING.md)。