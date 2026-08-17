# LiveOps Community Intelligence - 本地完整模式一键启动 (PowerShell)
# 用法: powershell -ExecutionPolicy Bypass -File scripts/start-local.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "== LiveOps CI 本地模式 ==" -ForegroundColor Cyan

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "错误: 未找到 uv，请先安装 https://docs.astral.sh/uv/" -ForegroundColor Red; exit 1
}
if (-not (Get-Command pnpm.cmd -ErrorAction SilentlyContinue)) {
    Write-Host "错误: 未找到 pnpm，请先安装 npm i -g pnpm" -ForegroundColor Red; exit 1
}
if (-not (Test-Path (Join-Path $root "runs"))) {
    Write-Host "提示: runs/ 为空，可用 tools/run_seed_analysis.py 重建演示任务" -ForegroundColor Yellow
}

Write-Host "[1/2] 后端 FastAPI  http://localhost:8000" -ForegroundColor Yellow
$back = Start-Process -FilePath "uv" -ArgumentList "run","uvicorn","liveops.api.main:app","--port","8000" `
    -WorkingDirectory (Join-Path $root "backend") -PassThru -WindowStyle Minimized

Write-Host "[2/2] 前端 Next.js  http://localhost:3000" -ForegroundColor Yellow
$front = Start-Process -FilePath "pnpm.cmd" -ArgumentList "dev" `
    -WorkingDirectory (Join-Path $root "frontend") -PassThru -WindowStyle Minimized

Start-Sleep -Seconds 5
Write-Host "已启动: http://localhost:3000 (在[数据与任务]页选择 seed-* 任务查看案例)" -ForegroundColor Green
Start-Process "http://localhost:3000"
Write-Host "按 Ctrl+C 停止。"
try {
    Wait-Process -Id $back.Id, $front.Id
} finally {
    Stop-Process -Id $back.Id, $front.Id -Force -ErrorAction SilentlyContinue
}
