#!/usr/bin/env bash
# LiveOps Community Intelligence — 本地完整模式一键启动 (Git Bash / WSL)
# 需要本机存在分析任务数据（runs/）。首次可用：
#   cd backend && uv run python tools/run_seed_analysis.py
# 真实 LLM 标注：先复制 .env.example 为 .env 并填写密钥。
set -e
cd "$(dirname "$0")/.."

echo "== LiveOps CI 本地模式 =="

# 依赖自检（给出可读错误而非堆栈）
if ! command -v uv >/dev/null 2>&1; then
  echo "错误: 未找到 uv。请先安装: https://docs.astral.sh/uv/"
  exit 1
fi
if ! command -v pnpm >/dev/null 2>&1; then
  echo "错误: 未找到 pnpm。请先安装: npm i -g pnpm"
  exit 1
fi
if [ -z "$(ls -A runs 2>/dev/null)" ]; then
  echo "提示: runs/ 为空，暂无可查看的分析任务。"
  echo "      可用 'cd backend && uv run python tools/run_seed_analysis.py' 重建两游戏演示任务。"
fi

echo "[1/2] 启动后端 FastAPI  http://localhost:8000"
(cd backend && uv run uvicorn liveops.api.main:app --port 8000) &
BACK_PID=$!

echo "[2/2] 启动前端 Next.js  http://localhost:3000"
(cd frontend && pnpm dev) &
FRONT_PID=$!

cleanup() {
  kill "$BACK_PID" "$FRONT_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

sleep 5
echo ""
echo "已启动：前端 http://localhost:3000 （后端 http://localhost:8000）"
echo "首次使用：在「数据与任务」页点击一个 seed-* 任务即可查看案例。"
echo "按 Ctrl+C 停止。"
wait
