"""规范化节点：清洗、去重（精确 + SimHash 近重复）、语言判断、垃圾标记、时间窗过滤。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date

from .schema import CommunityPost, PostFlag, StudyConfig

_CTRL_RE = re.compile(r"[\u200b\u200c\ufeff\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WS_RE = re.compile(r"[ \t\r]+")
_MULTI_NL = re.compile(r"\n{3,}")

LOTTERY_RE = re.compile(r"(抽奖|抽.{0,3}(奖|福利|卡片)|转发.{0,6}抽|关注.{0,6}抽|开奖|福利发放|中奖名单)")
AD_RE = re.compile(r"(加.{0,2}(微信|qq|vx)|代充|代练|低价点卡|出售账号|买号卖号|兼职|广告投放|点击链接购物)")
REPEAT_CHAR_RE = re.compile(r"(.)\1{19,}")  # 单字符连续 20+ 视为刷屏
EMOJI_ONLY_RE = re.compile(r"^[\W\U0001F000-\U0001FAFF\s]+$")


def clean_text(text: str) -> str:
    """控制字符/零宽字符清理 + 空白折叠。保留 emoji（情绪信号）与中文标点。"""
    t = _CTRL_RE.sub("", text)
    t = _WS_RE.sub(" ", t)
    t = _MULTI_NL.sub("\n\n", t)
    return t.strip()


def chinese_ratio(text: str) -> float:
    if not text:
        return 0.0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return cjk / max(len(text), 1)


def detect_flags(text: str, likes: int = 0) -> list[PostFlag]:
    flags: list[PostFlag] = []
    if LOTTERY_RE.search(text):
        flags.append(PostFlag.LOTTERY)
    if AD_RE.search(text):
        flags.append(PostFlag.AD)
    if REPEAT_CHAR_RE.search(text) or (len(text) <= 4 and EMOJI_ONLY_RE.match(text)):
        flags.append(PostFlag.SPAM)
    return flags


# ---------- SimHash 近重复 ----------

def _tokens(text: str) -> list[str]:
    t = re.sub(r"\s+", "", text.lower())
    if len(t) <= 2:
        return [t] if t else []
    return [t[i : i + 2] for i in range(len(t) - 1)]  # 字符二元组


def simhash64(text: str) -> int:
    bits = [0] * 64
    for tok in _tokens(text):
        h = int.from_bytes(hashlib.md5(tok.encode("utf-8")).digest()[:8], "big")
        for i in range(64):
            bits[i] += 1 if (h >> i) & 1 else -1
    v = 0
    for i in range(64):
        if bits[i] > 0:
            v |= 1 << i
    return v


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _fuzzy_dup(a: str, b: str) -> bool:
    """长度相近且序列相似度 ≥0.85 视为近重复（评论短文本场景）。"""
    la, lb = len(a), len(b)
    if abs(la - lb) > max(3, 0.15 * max(la, lb)):
        return False
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b, autojunk=False).ratio() >= 0.85


def exact_hash(text: str) -> str:
    return hashlib.sha1(re.sub(r"\s+", "", text).encode("utf-8")).hexdigest()[:16]


@dataclass
class NormalizeReport:
    total_in: int = 0
    kept: int = 0
    dropped_out_of_window: int = 0
    dropped_spam: int = 0
    duplicate_groups: int = 0
    duplicates_flagged: int = 0
    non_chinese: int = 0
    warnings: list[str] = field(default_factory=list)


def day_offset(t0: date, d: date) -> int:
    return (d - t0).days


def normalize_posts(
    posts: list[CommunityPost],
    study: StudyConfig,
    *,
    dedup_hamming: int = 3,
    drop_spam: bool = True,
) -> tuple[list[CommunityPost], NormalizeReport]:
    """时间窗过滤 → 清洗 → 垃圾标记/剔除 → 去重分组。

    - 时间窗外剔除（计数）。
    - spam 类默认剔除（抽奖/广告保留数据但通常 relevant=false，由标注判定；这里仅 spam 剔除）。
    - 精确重复直接剔除；SimHash 近重复保留首条，其余标记 duplicate 并归入 dedup_group。
    """
    rep = NormalizeReport(total_in=len(posts))

    # 1. 时间窗
    in_window: list[CommunityPost] = []
    for p in posts:
        off = day_offset(study.t0_date, p.published_at.date())
        if study.window.in_window(off):
            in_window.append(p)
        else:
            rep.dropped_out_of_window += 1

    # 2. 清洗 + 标记
    cleaned: list[CommunityPost] = []
    for p in in_window:
        text = clean_text(p.text)
        if not text:
            rep.dropped_spam += 1
            continue
        flags = list(p.flags)
        new_flags = detect_flags(text, p.likes)
        for f in new_flags:
            if f not in flags:
                flags.append(f)
        p2 = p.model_copy(update={"text": text, "flags": flags})
        if PostFlag.SPAM in flags:
            rep.dropped_spam += 1
            if not drop_spam:
                cleaned.append(p2)
            continue
        cleaned.append(p2)

    # 3. 去重：精确 hash + 长度分桶内序列相似度（短中文评论 SimHash 区分度不足）
    seen_exact: dict[str, str] = {}
    buckets: dict[int, list[tuple[str, str]]] = {}  # len//6 -> [(代表文本, gid)]
    result: list[CommunityPost] = []
    group_count = 0
    for p in cleaned:
        eh = exact_hash(p.text)
        if eh in seen_exact:
            gid = seen_exact[eh]
            rep.duplicates_flagged += 1
            result.append(p.model_copy(update={"dedup_group": gid, "flags": [*p.flags, PostFlag.DUPLICATE]}))
            continue
        gid = None
        key = len(p.text) // 6
        for k in (key - 1, key, key + 1):
            for rep_text, g2 in buckets.get(k, []):
                if _fuzzy_dup(p.text, rep_text):
                    gid = g2
                    break
            if gid:
                break
        if gid is None:
            gid = f"dg-{eh[:8]}"
            group_count += 1
            buckets.setdefault(key, []).append((p.text, gid))
            seen_exact[eh] = gid
            result.append(p.model_copy(update={"dedup_group": gid}))
        else:
            seen_exact[eh] = gid
            rep.duplicates_flagged += 1
            result.append(
                p.model_copy(update={"dedup_group": gid, "flags": [*p.flags, PostFlag.DUPLICATE]})
            )

    rep.duplicate_groups = group_count
    rep.kept = len(result)
    rep.non_chinese = sum(1 for p in result if chinese_ratio(p.text) < 0.15)
    return result, rep


def effective_posts(posts: list[CommunityPost]) -> list[CommunityPost]:
    """指标聚合用的有效样本：非 duplicate、非 spam、非 lottery/ad（相关性另有标注）。"""
    return [
        p for p in posts
        if PostFlag.DUPLICATE not in p.flags
        and PostFlag.SPAM not in p.flags
        and PostFlag.LOTTERY not in p.flags
        and PostFlag.AD not in p.flags
    ]
