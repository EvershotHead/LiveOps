#!/usr/bin/env bash
# 公开演示站构建（静态导出，GitHub Pages 部署用）
# 用法: bash scripts/build-demo.sh [BASE_PATH]
# 示例: bash scripts/build-demo.sh /liveops-community-intelligence
set -e
cd "$(dirname "$0")/.."

BASE_PATH="${1:-}"
export NEXT_PUBLIC_DEMO=1
export NEXT_PUBLIC_BASE_PATH="$BASE_PATH"

echo "== 构建公开演示（只读，无密钥）=="
# 1) 刷新演示数据（从 runs/seed-* 重导出）
(cd backend && uv run python tools/export_demo.py)

# 2) 静态构建（复制 public-data 进 out）
cd frontend
pnpm build
mkdir -p public/public-data
cp -r ../demo/public-data/* public/public-data/
pnpm build
echo "完成：frontend/out/ 即可发布到 GitHub Pages（base path: ${BASE_PATH:-/}）"
