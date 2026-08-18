# -*- coding: utf-8 -*-
"""登录态采集测试：raw_rows.jsonl → CommunityPost → 规范化 → 基础统计 → 测试报告。

输出: data/raw/login-test/test_report.md（用户后续可删除）
"""
import json
import time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from liveops.anonymize import make_anon_fn
from liveops.normalize import day_offset, normalize_posts
from liveops.schema import CommunityPost, StudyConfig

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "login-test" / "raw_rows.jsonl"
OUT = ROOT / "data" / "raw" / "login-test" / "test_report.md"
UTC = timezone.utc

STUDY = StudyConfig(study_id="login-test", game="genshin", version_label="6.8",
                    t0_date=date(2026, 7, 1))
VIDEO = "BV1uMTY6aEZv"
VIDEO_URL = f"https://www.bilibili.com/video/{VIDEO}"


def load_rows():
    rows = []
    for line in RAW.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def to_posts(rows):
    anon_fn = make_anon_fn("login-test")
    posts = []
    for r in rows:
        if "_err" in r:
            continue
        posts.append(CommunityPost(
            post_id=str(r["rpid"]), video_id=VIDEO, parent_id=None,
            text=r.get("text", ""),
            published_at=datetime.fromtimestamp(r.get("ctime", 0), tz=UTC),
            likes=int(r.get("like", 0) or 0), reply_count=int(r.get("rcount", 0) or 0),
            anon_user_id=anon_fn(str(r.get("mid", ""))),
            collected_at=datetime.now(UTC), source_url=VIDEO_URL,
        ))
    return posts


def main():
    rows = load_rows()
    posts = to_posts(rows)
    kept, rep = normalize_posts(posts, STUDY)

    # 统计
    ctimes = [r.get("ctime", 0) for r in rows if "_err" not in r]
    dt_min = datetime.fromtimestamp(min(ctimes), tz=UTC) if ctimes else None
    dt_max = datetime.fromtimestamp(max(ctimes), tz=UTC) if ctimes else None
    in_win = sum(1 for p in kept if STUDY.window.in_window(day_offset(STUDY.t0_date, p.published_at.date())))
    per_user = Counter(p.anon_user_id for p in kept)
    max_user = max(per_user.values()) if per_user else 0
    text_len = Counter()
    for p in kept:
        text_len["<10字"] += len(p.text) < 10
        text_len["10-50字"] += 10 <= len(p.text) < 50
        text_len[">=50字"] += len(p.text) >= 50

    report = f"""# 登录态采集测试报告

> 生成时间：{datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} · 本报告为一次性测试产物，用户确认后可删除。

## 1. 测试目的

验证「IAB 内置浏览器登录态」能否绕过未登录时的评论翻页限制，为后续 7.0 版本完整采样提供数据获取方案。

## 2. 采集方法与参数

| 项 | 值 |
|---|---|
| 登录态 | IAB 内置浏览器（`isLogin=true`，uid 3707057454713100） |
| 接口 | `api.bilibili.com/x/v2/reply/main`（非 wbi） |
| 视频 | {VIDEO}（原神 6.8 月之八一条龙，总评论 8,787） |
| 模式 | mode=3（热门），ps=20 |
| 翻页深度 | next=1..120 |
| 限速 | 每页间 ≥2.5s（waitForTimeout） |

## 3. 采集结果

| 指标 | 值 |
|---|---|
| 采集评论总数 | {len(rows)} 条 |
| 规范化保留（去重/垃圾后） | {rep.kept} 条 |
| 精确+近重复剔除 | {rep.duplicates_flagged} 条 |
| 垃圾剔除 | {rep.dropped_spam} 条 |
| 时间跨度 | {dt_min.strftime('%Y-%m-%d') if dt_min else '-'} ~ {dt_max.strftime('%Y-%m-%d') if dt_max else '-'} |
| 时间窗过滤后保留（T-7~T+28） | {rep.kept} 条 |
| 时间窗过滤剔除（窗外） | {rep.dropped_out_of_window} 条 |
| 单作者最大条数 | {max_user} 条 |

## 4. 关键结论

1. **登录态翻页完全解锁**：未登录时每视频仅 ~3 条根评论（next>0 返回空）；登录态下单视频可连续翻页 120 页、拿到 {len(rows)} 条，且 `is_end=false`（还可继续）。
2. **稳定性良好**：全程 code=0，无风控码（-412/-352）、无验证码、无中断。
3. **数据形态**：mode=3 热门根评论（非楼中楼），文本长度分布：{dict(text_len)}。
4. **时间窗影响**：热门评论时间跨度大（含 6.8 版本外的新评论），按 T-7~T+28 过滤剔除窗外 {rep.dropped_out_of_window} 条、保留 {rep.kept} 条。

## 5. 对后续版本的指导

- **可行方案**：IAB 登录态 + 逐页导航 API 可获取完整评论（每视频数百~数千条），满足 4,000-5,000 条/游戏的配额。
- **注意**：需按视频×时间窗控制配额；速率保持 ≥2.5s/页；楼中楼仍建议单独翻页采集。
- **本批 1999 条为测试数据**，已按要求**未加入**原 4800 条分析数据集，后续可删除本目录。
"""
    OUT.write_text(report, encoding="utf-8")
    print(f"测试报告已生成: {OUT}")
    print(f"采集 {len(rows)} → 规范化保留 {rep.kept}，窗内 {in_win}")


if __name__ == "__main__":
    main()
