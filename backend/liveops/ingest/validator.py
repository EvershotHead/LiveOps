"""Schema 校验：canonical 行 → CommunityPost / ContentItem 列表 + 行号级错误报告。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from dateutil import parser as dateparser

from ..schema import CommunityPost, PostFlag
from ..config import OVERLENGTH_THRESHOLD
from .mapping import REQUIRED_FIELDS


@dataclass
class ValidationReport:
    total_rows: int = 0
    valid_count: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)  # {row, field, message}
    posts: list[CommunityPost] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.valid_count > 0 and not any(e["severity"] == "fatal" for e in self.errors)

    def summary(self) -> str:
        return (
            f"共 {self.total_rows} 行，有效 {self.valid_count} 行，"
            f"错误 {len(self.errors)} 处"
        )


def _parse_dt(v: Any) -> datetime | None:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, (int, float)):
        # B 站 ctime 为秒级时间戳
        try:
            return datetime.fromtimestamp(float(v), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(v, str) and v.strip():
        try:
            dt = dateparser.parse(v.strip())
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except (ValueError, OverflowError):
            return None
    return None


def validate_posts(
    rows: list[dict[str, Any]],
    *,
    default_video_id: str = "imported",
    anon_salt_fn=None,
) -> ValidationReport:
    """把映射后的行转成 CommunityPost。最少必需 text/published_at/source_url。"""
    report = ValidationReport(total_rows=len(rows))
    for i, row in enumerate(rows, 1):
        missing = [f for f in REQUIRED_FIELDS if not str(row.get(f) or "").strip()]
        if missing:
            report.errors.append({
                "row": i, "field": ",".join(missing),
                "message": f"缺少必需字段: {missing}",
                "severity": "fatal",
            })
            continue
        text = str(row["text"])
        if not text.strip():
            report.errors.append({"row": i, "field": "text", "message": "正文为空", "severity": "fatal"})
            continue
        dt = _parse_dt(row.get("published_at"))
        if dt is None:
            report.errors.append({
                "row": i, "field": "published_at",
                "message": f"无法解析时间: {row.get('published_at')!r}",
                "severity": "fatal",
            })
            continue
        flags: list[PostFlag] = []
        if len(text) > OVERLENGTH_THRESHOLD:
            flags.append(PostFlag.OVERLENGTH)
        user_key = str(row.get("user_key") or "unknown")
        anon_id = anon_salt_fn(user_key) if anon_salt_fn else _fallback_anon(user_key)
        try:
            post = CommunityPost(
                post_id=str(row.get("post_id") or f"imported-{i:06d}"),
                video_id=str(row.get("video_id") or default_video_id),
                parent_id=str(row["parent_id"]) if row.get("parent_id") else None,
                text=text,
                published_at=dt,
                likes=int(row.get("likes") or 0),
                reply_count=int(row.get("reply_count") or 0),
                anon_user_id=anon_id,
                collected_at=datetime.now(timezone.utc),
                dedup_group=str(row["dedup_group"]) if row.get("dedup_group") else None,
                flags=flags,
                source_url=str(row["source_url"]),
            )
        except Exception as e:  # pydantic ValidationError 等
            report.errors.append({"row": i, "field": "*", "message": str(e)[:200], "severity": "fatal"})
            continue
        report.posts.append(post)
        report.valid_count += 1
    return report


def _fallback_anon(user_key: str) -> str:
    """无盐回退（导入模式且未配置 study 时）——仍不可逆，但强度低于 HMAC。"""
    import hashlib
    return hashlib.sha256(("fallback:" + user_key).encode("utf-8")).hexdigest()[:16]
