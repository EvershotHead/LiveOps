#!/usr/bin/env bash
# LiveOps Community Intelligence — 本地一键启动 (Git Bash / WSL)
set -e
cd "$(dirname "$0")/.."

echo "== LiveOps CI 本地模式启动 =="
echo "[1/3] 后端 FastAPI :8000"
(cd backend && uv run uvicorn liveops.api.main:app --port 8000 &
 BACK_PID=$!
 echo "[2/3] 前端 Next.js :3000"
 cd frontend && pnpm dev
 kill $BACK_PID 2>/dev/null || true) &
echo "[3/3] 访问 http://localhost:3000"
echo "提示：真实 LLM 标注需先在 .env 配置 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL。"
wait
