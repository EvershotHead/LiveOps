"""字段映射：RawTable + 用户确认的映射 → MappedTable（CommunityPost 前身行）。

- AI 可推荐映射（suggest_mapping，基于列名相似度 + 可选 LLM），
  但必须用户确认后生效（API 层职责），本模块只做纯函数计算。
- 最少必需：text / published_at / source_url。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .readers import RawTable

REQUIRED_FIELDS = ["text", "published_at", "source_url"]

# 常见别名（中英文）→ Canonical 字段
_ALIAS: dict[str, list[str]] = {
    "text": ["text", "content", "评论", "评论内容", "正文", "message", "body", "comment", "msg"],
    "published_at": ["published_at", "publish_time", "ctime", "时间", "评论时间", "发布时间", "created_at", "time", "datetime", "date"],
    "source_url": ["source_url", "url", "链接", "来源", "视频链接", "source", "link"],
    "post_id": ["post_id", "rpid", "id", "评论id", "comment_id"],
    "video_id": ["video_id", "bvid", "bv号", "avid", "视频id"],
    "parent_id": ["parent_id", "parent", "root", "父评论", "reply_to"],
    "likes": ["likes", "like", "点赞", "点赞数", "like_count", "赞"],
    "reply_count": ["reply_count", "replies", "回复数", "回复"],
    "user_key": ["user_key", "uid", "mid", "用户id", "user_id", "author"],
    "dedup_group": ["dedup_group", "去重组"],
}


def _norm(s: str) -> str:
    return re.sub(r"[\s_\-（）()：:]", "", str(s)).strip().lower()


def suggest_mapping(table: RawTable) -> dict[str, str | None]:
    """基于列名别名匹配的确定性推荐（不调用 LLM，可复现）。"""
    mapping: dict[str, str | None] = {}
    norm_cols = {_norm(c): c for c in table.columns}
    for canon, aliases in _ALIAS.items():
        hit = None
        for a in aliases:
            if _norm(a) in norm_cols:
                hit = norm_cols[_norm(a)]
                break
        mapping[canon] = hit
    return mapping


@dataclass
class MappingResult:
    mapping: dict[str, str | None]          # canonical -> 源列名
    missing_required: list[str] = field(default_factory=list)


def apply_mapping(table: RawTable, mapping: dict[str, str | None]) -> MappingResult:
    missing = [f for f in REQUIRED_FIELDS if not mapping.get(f)]
    return MappingResult(mapping=dict(mapping), missing_required=missing)


def project_rows(table: RawTable, mapping: dict[str, str | None]) -> list[dict[str, Any]]:
    """按映射投影为 canonical 行；未映射的可选字段给默认值。"""
    out: list[dict[str, Any]] = []
    for r in table.rows:
        row: dict[str, Any] = {}
        for canon, src in mapping.items():
            if src and src in r:
                row[canon] = r[src]
        out.append(row)
    return out
