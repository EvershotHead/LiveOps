# LiveOps Community Intelligence — 本地一键启动
# 用法: powershell -ExecutionPolicy Bypass -File scripts\start-local.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "== LiveOps CI 本地模式启动 ==" -ForegroundColor Cyan

# 1) 后端（FastAPI :8000）
Write-Host "[1/3] 启动后端 FastAPI (http://localhost:8000) ..." -ForegroundColor Yellow
$backend = Start-Process -PassThru -NoNewWindow pwsh -ArgumentList "-Command", "cd '$root\backend'; uv run uvicorn liveops.api.main:app --port 8000"
Start-Sleep -Seconds 3

# 2) 前端（Next.js :3000，本地模式）
Write-Host "[2/3] 启动前端 Next.js (http://localhost:3000) ..." -ForegroundColor Yellow
$frontend = Start-Process -PassThru -NoNewWindow pwsh -ArgumentList "-Command", "cd '$root\frontend'; pnpm dev"

# 3) 浏览器
Write-Host "[3/3] 打开 http://localhost:3000" -ForegroundColor Yellow
Start-Process "http://localhost:3000"

Write-Host ""
Write-Host "已启动。停止：关闭两个窗口，或运行 Stop-Process $($backend.Id), $($frontend.Id)"
Write-Host "提示：如需真实 LLM 标注，请先在 .env 填写 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 后重启。"
