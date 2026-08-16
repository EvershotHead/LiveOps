"""全局配置：路径、环境变量、指标权重默认值。

权重是可配置的运营排序规则，不是客观事实；UI 必须展示分项与敏感性。
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("LIVEOPS_DATA", REPO_ROOT / "data"))
RUNS_DIR = Path(os.environ.get("LIVEOPS_RUNS", REPO_ROOT / "runs"))
DEMO_DATA_DIR = REPO_ROOT / "demo" / "public-data"
SECRETS_DIR = Path(os.environ.get("LIVEOPS_SECRETS", REPO_ROOT / "secrets"))

# ---------- LLM ----------
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "")
LLM_STRONG_MODEL = os.environ.get("LLM_STRONG_MODEL", "") or LLM_MODEL
EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-m3")

# ---------- 模式 ----------
MODE = os.environ.get("LIVEOPS_MODE", "local")  # local | demo

# ---------- 指标组合权重（可被 config/weights.json 覆盖） ----------
ISSUE_PRIORITY_WEIGHTS = {
    "oppose_intensity": 0.30,   # 反对强度
    "topic_share": 0.25,        # 主题占比
    "growth": 0.20,             # 增长速度
    "engagement": 0.15,         # 互动影响
    "persistence": 0.10,        # 持续性
}
OPPORTUNITY_WEIGHTS = {
    "support_rate": 0.35,       # 支持率
    "topic_growth": 0.25,       # 主题增长
    "video_coverage": 0.20,     # 视频覆盖
    "engagement": 0.10,         # 互动影响
    "persistence": 0.10,        # 持续性
}

# ---------- 分析参数 ----------
OVERLENGTH_THRESHOLD = 2000        # 超过该字符数标记 overlength
ANALYSIS_TEXT_WINDOW = 1200        # 送模型的文本窗口（全文留档）
MIN_NEW_TOPIC_CLUSTER_SIZE = 5     # 新兴主题候选最小簇大小（夹具/小样本用小值）
EMBED_COSINE_ASSIGN_THRESHOLD = 0.55

# ---------- LLM 客户端 ----------
LLM_MAX_RETRIES = 5
LLM_BACKOFF_BASE_S = 1.5
LLM_TIMEOUT_S = 120
ROUTE_REVIEW_MIN_CONFIDENCE = 0.60
ROUTE_REVIEW_LIKE_PERCENTILE = 95


def weights_path() -> Path:
    return REPO_ROOT / "config" / "weights.json"
