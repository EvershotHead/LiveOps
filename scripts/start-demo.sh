#!/usr/bin/env bash
# LiveOps Community Intelligence — 公开演示模式一键启动（无密钥、开箱即看）
# 静态导出 + 本地静态服务，数据来自已提交的 demo/public-data（匿名化、只读）。
# 用法: bash scripts/start-demo.sh [端口]   默认 4173
set -e
cd "$(dirname "$0")/.."
PORT="${1:-4173}"

echo "== LiveOps CI 公开演示模式（无密钥只读） =="

if ! command -v pnpm >/dev/null 2>&1; then
  echo "错误: 未找到 pnpm。请先安装: npm i -g pnpm"
  exit 1
fi

# 1) 首次或数据变化时构建静态站
if [ ! -d "frontend/out" ]; then
  echo "[1/3] 首次构建演示静态站（约 1-2 分钟）..."
  (cd frontend && mkdir -p public/public-data \
    && cp -r ../demo/public-data/* public/public-data/ \
    && NEXT_PUBLIC_DEMO=1 pnpm build)
else
  echo "[1/3] 演示静态站已存在，跳过构建"
fi

# 2) 启动静态服务
echo "[2/3] 启动静态服务 http://localhost:${PORT}"
(cd frontend && pnpm exec serve out -l "${PORT}" --no-clipboard) &
SERVE_PID=$!
trap 'kill "$SERVE_PID" 2>/dev/null || true' EXIT INT TERM

sleep 3

# 3) 尝试在默认浏览器打开（失败也不阻塞）
echo "[3/3] 打开浏览器..."
( cmd.exe /c start "" "http://localhost:${PORT}" 2>/dev/null || \
  xdg-open "http://localhost:${PORT}" 2>/dev/null || \
  open "http://localhost:${PORT}" 2>/dev/null || true )

echo ""
echo "演示站已就绪：http://localhost:${PORT}  （左上角可切换 原神 6.8 / 鸣潮 3.5）"
echo "按 Ctrl+C 停止。"
wait
