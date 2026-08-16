"""不可逆匿名化与公开导出泄漏扫描。

- anon_id: HMAC-SHA256(study 盐, user_key)[:16]；盐存 secrets/（gitignore），公开数据无盐不可反推。
- 采集/导入时立即匿名化，原始 uid 永不落盘。
- 公开导出前强制泄漏扫描（字段白名单 + PII 正则），断言通过才允许导出。
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets as pysecrets
from pathlib import Path
from typing import Any

from . import config

# 公开数据禁止出现的字段名（含嵌套）
FORBIDDEN_KEYS = {
    "uname", "mid", "uid", "avatar", "face", "avatar_url", "face_url",
    "user_name", "username", "profile", "homepage", "follower", "fans",
    "sex", "level", "vip", "pendant", "official", "sign",
}

# 文本中的潜在 PII 模式
UID_TEXT_RE = re.compile(r"(UID[:：\s]*\d{6,12}|空间号[:：\s]*\d{6,12})")
MENTION_RE = re.compile(r"@([^\s@，。,！!？?]{1,30})")
QQ_WECHAT_RE = re.compile(r"(?:QQ|vx|微信|V信)[:：\s]*[0-9a-zA-Z_\-]{5,}", re.IGNORECASE)


def get_or_create_salt(study_id: str) -> bytes:
    salts_dir = config.SECRETS_DIR
    salts_dir.mkdir(parents=True, exist_ok=True)
    p = salts_dir / f"{study_id}.salt"
    if p.exists():
        return bytes.fromhex(p.read_text(encoding="utf-8").strip())
    salt = pysecrets.token_hex(32)
    p.write_text(salt, encoding="utf-8")
    try:  # best-effort windows 权限收紧
        import os
        os.chmod(p, 0o600)
    except OSError:
        pass
    return bytes.fromhex(salt)


def anon_id(salt: bytes, user_key: str) -> str:
    return hmac.new(salt, user_key.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def make_anon_fn(study_id: str):
    salt = get_or_create_salt(study_id)
    return lambda user_key: anon_id(salt, user_key)


def mask_text(text: str) -> str:
    """公开导出的文本脱敏：@提及、QQ/微信号、显式 UID。"""
    t = MENTION_RE.sub("@***", text)
    t = QQ_WECHAT_RE.sub("***", t)
    t = UID_TEXT_RE.sub("UID:***", t)
    return t


# ---------- 泄漏扫描 ----------

class LeakError(Exception):
    pass


def _iter_keys(obj: Any, path: str = ""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{path}.{k}" if path else str(k), v
            yield from _iter_keys(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _iter_keys(v, f"{path}[{i}]")


def scan_for_leaks(obj: Any) -> list[str]:
    """返回所有泄漏点描述；空列表 = 干净。"""
    leaks: list[str] = []
    for key_path, value in _iter_keys(obj):
        leaf = key_path.split(".")[-1].split("[")[0].lower()
        if leaf in FORBIDDEN_KEYS:
            leaks.append(f"禁止字段: {key_path}")
        if isinstance(value, str):
            if UID_TEXT_RE.search(value):
                leaks.append(f"文本含 UID: {key_path}")
            if QQ_WECHAT_RE.search(value):
                leaks.append(f"文本含联系方式: {key_path}")
            if re.search(r"space\.bilibili\.com/\d+", value):
                leaks.append(f"用户主页链接: {key_path}")
            if MENTION_RE.search(value) and "@" in value and "***" not in value:
                leaks.append(f"文本含未脱敏 @提及: {key_path}")
    return leaks


def assert_no_pii(obj: Any) -> None:
    leaks = scan_for_leaks(obj)
    if leaks:
        raise LeakError("公开导出泄漏扫描未通过:\n" + "\n".join(leaks[:20]))


def build_public_export(
    posts: list[dict],
    videos: list[dict],
    metrics: dict | None = None,
) -> dict:
    """构建公开数据包：白名单字段 + 文本脱敏，然后强制扫描。"""
    pub_videos = []
    for v in videos:
        pub_videos.append({
            "video_id": v["video_id"], "title": v["title"], "url": v["url"],
            "published_at": v["published_at"], "category": v["category"],
            "author_type": v["author_type"], "stats_snapshot": {
                k: v.get("stats_snapshot", {}).get(k, 0)
                for k in ("view", "like", "coin", "favorite", "share", "comment")
            },
        })
    pub_posts = []
    for p in posts:
        pub_posts.append({
            "post_id": p["post_id"], "video_id": p["video_id"],
            "parent_id": p.get("parent_id"), "text": mask_text(p["text"]),
            "published_at": p["published_at"], "likes": p.get("likes", 0),
            "reply_count": p.get("reply_count", 0),
            "anon_user_id": p.get("anon_user_id", "x" * 16),
            "dedup_group": p.get("dedup_group"), "flags": p.get("flags", []),
            "source_url": p["source_url"], "synthetic": p.get("synthetic", False),
        })
    export = {"videos": pub_videos, "posts": pub_posts}
    if metrics is not None:
        # metrics 中的 evidence_items 已只含匿名化片段，但仍复扫
        export["metrics"] = metrics
    assert_no_pii(export)
    return export
