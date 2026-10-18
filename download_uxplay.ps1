# 下载预编译 uxplay（GStreamer 版 1.73.6，CLI 参数兼容 -n / -fs / -fps / -vsync no）
# 来源: https://github.com/yztshh/Uxplay-airplay/releases/tag/v1.73.6-windows-1
# 用法: powershell -ExecutionPolicy Bypass -File download_uxplay.ps1
# 注意: 该版本依赖 Apple Bonjour 服务（包内附带 1-安装Bonjour.bat，也可用
#       winget install --id Apple.Bonjour -e 安装）
$ErrorActionPreference = 'Stop'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$outDir = Join-Path $dir 'uxplay'
$zip = Join-Path $env:TEMP 'uxplay-windows-sdl.zip'
$url = 'https://github.com/yztshh/Uxplay-airplay/releases/download/v1.73.6-windows-1/UxPlay-Windows-1.73.6-final.zip'

Write-Host "Downloading $url ..."
Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $zip

$tmp = Join-Path $env:TEMP 'uxplay-windows-sdl-extract'
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
Expand-Archive -Path $zip -DestinationPath $tmp

if (Test-Path $outDir) { Remove-Item $outDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$pkg = Get-ChildItem $tmp -Directory | Select-Object -First 1
Get-ChildItem $pkg.FullName -Force | Copy-Item -Destination $outDir -Recurse -Force

Write-Host "Done. uxplay.exe is now at: $outDir\uxplay.exe"
