"""FastAPI 入口：本地完整模式 / 公开演示只读模式。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .. import config
from . import routes_read, routes_review, routes_runs

app = FastAPI(title="LiveOps Community Intelligence", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"], allow_headers=["*"],
)

app.include_router(routes_runs.router)
app.include_router(routes_read.router)
app.include_router(routes_review.router)


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "mode": config.MODE,
        "llm_configured": bool(config.LLM_BASE_URL and config.LLM_API_KEY and config.LLM_MODEL),
    }


@app.get("/api/mode")
def mode():
    """前端启动时探测：demo 只读（隐藏导入/审核入口），local 完整。"""
    return {"mode": config.MODE, "read_only": config.MODE == "demo"}
