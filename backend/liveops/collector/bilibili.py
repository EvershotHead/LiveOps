"""B 站公开接口采集器（传输层注入式，不绑定具体 HTTP/浏览器实现）。

合规护栏：
- 限速由调用方 TokenBucket 强制（评论 ≥2.5s，元数据 ≥1.5s）。
- 风控信号（code -412/-352、验证码特征）→ CollectorHardStop，禁止重试。
- 解析容错：接口字段缺失/结构漂移返回空结果并记 journal，不崩溃
  （不稳定即切换导入模式的协议条款）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from ..schema import CommunityPost, ContentItem, VideoCategory
from .journal import CollectionJournal
from .ratelimit import TokenBucket

JsonFetcher = Callable[[str], dict]   # url -> parsed json

SEARCH_URL = "https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword={kw}&page={page}"
VIEW_URL = "https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
REPLY_MAIN_URL = "https://api.bilibili.com/x/v2/reply/main?oid={oid}&type=1&mode={mode}&next={next}&ps=20"

RISK_CODES = {-412, -352, -411, 9, -799}  # 风控/请求被拒/账号异常等


class CollectorHardStop(Exception):
    """命中风控信号：立即停止采集，禁止重试、禁止换 UA 绕过。"""


@dataclass
class ParsedComment:
    post_id: str
    parent_id: str | None
    text: str
    ctime: int
    likes: int
    reply_count: int
    user_key: str


def check_risk(payload: dict) -> None:
    code = payload.get("code")
    if code in RISK_CODES:
        raise CollectorHardStop(f"风控信号 code={code}，按协议硬停止采集")
    if isinstance(payload.get("data"), dict) and payload["data"].get("code") in RISK_CODES:
        raise CollectorHardStop("响应体内风控信号，按协议硬停止采集")


def _strip_html(title: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", title or "").strip()


# ---------- 搜索 ----------

def search_videos(fetch: JsonFetcher, keyword: str, page: int = 1) -> list[dict]:
    url = SEARCH_URL.format(kw=keyword, page=page)
    payload = fetch(url)
    check_risk(payload)
    if payload.get("code") != 0:
        return []
    results = (payload.get("data") or {}).get("result") or []
    out = []
    for r in results:
        if r.get("type") != "video":
            continue
        out.append({
            "bvid": r.get("bvid", ""),
            "title": _strip_html(r.get("title", "")),
            "author": r.get("author", ""),
            "mid": str(r.get("mid", "")),
            "pubdate": r.get("pubdate", 0),
            "play": int(r.get("play", 0) or 0),
            "review": int(r.get("review", 0) or 0),
            "rank": len(out) + 1,
        })
    return out


# ---------- 视频元数据 ----------

def fetch_video_meta(fetch: JsonFetcher, bvid: str) -> dict | None:
    payload = fetch(VIEW_URL.format(bvid=bvid))
    check_risk(payload)
    if payload.get("code") != 0:
        return None
    d = payload.get("data") or {}
    return {
        "bvid": d.get("bvid", bvid),
        "aid": d.get("aid", 0),
        "title": _strip_html(d.get("title", "")),
        "pubdate": d.get("pubdate", 0),
        "owner_mid": str((d.get("owner") or {}).get("mid", "")),
        "owner_name": (d.get("owner") or {}).get("name", ""),
        "stat": {
            "view": d.get("stat", {}).get("view", 0),
            "like": d.get("stat", {}).get("like", 0),
            "coin": d.get("stat", {}).get("coin", 0),
            "favorite": d.get("stat", {}).get("favorite", 0),
            "share": d.get("stat", {}).get("share", 0),
            "reply": d.get("stat", {}).get("reply", 0),
        },
    }


# ---------- 评论 ----------

def parse_comment(replies: Any) -> list[ParsedComment]:
    out: list[ParsedComment] = []
    for r in replies or []:
        if not isinstance(r, dict):
            continue
        content = r.get("content") or {}
        msg = (content.get("message") or "").strip()
        if not msg:
            continue
        out.append(ParsedComment(
            post_id=str(r.get("rpid", "")),
            parent_id=str(r["parent"]) if r.get("parent") and str(r.get("parent")) != "0" else None,
            text=msg,
            ctime=int(r.get("ctime", 0) or 0),
            likes=int(r.get("like", 0) or 0),
            reply_count=int(r.get("rcount", 0) or 0),
            user_key=str((r.get("member") or {}).get("mid", "")),
        ))
    return out


def fetch_comments_page(fetch: JsonFetcher, oid: int, *, mode: int = 3, next_page: int = 1) -> dict:
    """mode=3 热门，mode=2 时间。返回 roots + 楼中楼 replies + cursor。"""
    url = REPLY_MAIN_URL.format(oid=oid, mode=mode, next=next_page, ps=20)
    payload = fetch(url)
    check_risk(payload)
    if payload.get("code") != 0:
        return {"roots": [], "replies": [], "is_end": True, "all_count": 0}
    d = payload.get("data") or {}
    cursor = d.get("cursor") or {}
    roots = parse_comment(d.get("replies"))
    # 置顶评论不采（非自然排序）；无 replies 视为到达末页（结构漂移容错）
    return {
        "roots": roots,
        "replies": [],
        "is_end": bool(cursor.get("is_end")) or not roots,
        "next": cursor.get("next"),
        "all_count": cursor.get("all_count", 0),
    }


def fetch_sub_replies(fetch: JsonFetcher, oid: int, root_rpid: str, next_page: int = 1) -> dict:
    """楼中楼：x/v2/reply/reply 接口。"""
    url = (f"https://api.bilibili.com/x/v2/reply/reply?oid={oid}&type=1&root={root_rpid}"
           f"&pn={next_page}&ps=20")
    payload = fetch(url)
    check_risk(payload)
    if payload.get("code") != 0:
        return {"replies": [], "is_end": True}
    d = payload.get("data") or {}
    return {
        "replies": parse_comment(d.get("replies")),
        "is_end": not d.get("page", {}).get("count", 0) or next_page * 20 >= d.get("page", {}).get("count", 0),
    }


# ---------- 编排 ----------

@dataclass
class CollectorLimits:
    comment_interval_s: float = 2.5
    meta_interval_s: float = 1.5
    max_requests_per_session: int = 2000
    max_comments_per_video: int = 400
    max_comments_per_user: int = 10


@dataclass
class CollectionSession:
    fetch: JsonFetcher
    journal: CollectionJournal
    limits: CollectorLimits = field(default_factory=CollectorLimits)
    _comment_bucket: TokenBucket | None = None
    _meta_bucket: TokenBucket | None = None
    _requests: int = 0
    _hard_stopped: bool = False

    def __post_init__(self):
        self._comment_bucket = TokenBucket(self.limits.comment_interval_s)
        self._meta_bucket = TokenBucket(self.limits.meta_interval_s)

    def _guard(self, bucket: TokenBucket) -> None:
        if self._hard_stopped:
            raise CollectorHardStop("会话已硬停止，禁止继续采集")
        self._requests += 1
        if self._requests > self.limits.max_requests_per_session:
            raise CollectorHardStop("会话请求上限，停止（断点续采）")
        bucket.acquire(wait=True)

    # —— 元数据 ——
    def get_meta(self, bvid: str) -> dict | None:
        self._guard(self._meta_bucket)  # type: ignore[arg-type]
        try:
            meta = fetch_video_meta(self.fetch, bvid)
        except CollectorHardStop:
            self._hard_stopped = True
            self.journal.log("hard_stop", url=bvid, detail={"stage": "meta"})
            raise
        self.journal.log("meta", url=bvid, items=1 if meta else 0, video_id=bvid)
        return meta

    # —— 评论 ——
    def get_comment_page(self, oid: int, video_id: str, mode: int, page: int) -> dict:
        if self.journal.has_page(video_id, f"mode{mode}", page):
            return {"roots": [], "replies": [], "is_end": True, "skip": True}
        self._guard(self._comment_bucket)  # type: ignore[arg-type]
        url = REPLY_MAIN_URL.format(oid=oid, mode=mode, next=page)
        try:
            res = fetch_comments_page(self.fetch, oid, mode=mode, next_page=page)
        except CollectorHardStop:
            self._hard_stopped = True
            self.journal.log("hard_stop", url=url, page=page, video_id=video_id, mode=f"mode{mode}")
            raise
        self.journal.log("comment", url=url, page=page,
                          items=len(res["roots"]), video_id=video_id, mode=f"mode{mode}",
                          post_ids=[c.post_id for c in res["roots"]])
        return res

    def get_sub_replies(self, oid: int, video_id: str, root_rpid: str, page: int) -> dict:
        if self.journal.has_page(video_id, f"sub-{root_rpid}", page):
            return {"replies": [], "is_end": True, "skip": True}
        self._guard(self._comment_bucket)  # type: ignore[arg-type]
        url = f"https://api.bilibili.com/x/v2/reply/reply?oid={oid}&root={root_rpid}&pn={page}"
        try:
            res = fetch_sub_replies(self.fetch, oid, root_rpid, page)
        except CollectorHardStop:
            self._hard_stopped = True
            self.journal.log("hard_stop", url=url, page=page, video_id=video_id, mode=f"sub-{root_rpid}")
            raise
        self.journal.log("comment", url=url, page=page,
                          items=len(res["replies"]), video_id=video_id, mode=f"sub-{root_rpid}",
                          post_ids=[c.post_id for c in res["replies"]])
        return res


def comment_to_post(c: ParsedComment, video: ContentItem, anon_fn: Callable[[str], str]) -> CommunityPost:
    return CommunityPost(
        post_id=c.post_id,
        video_id=video.video_id,
        parent_id=c.parent_id,
        text=c.text,
        published_at=datetime.fromtimestamp(c.ctime, tz=timezone.utc) if c.ctime else datetime.now(timezone.utc),
        likes=c.likes,
        reply_count=c.reply_count,
        anon_user_id=anon_fn(c.user_key),
        collected_at=datetime.now(timezone.utc),
        source_url=video.url,
    )
