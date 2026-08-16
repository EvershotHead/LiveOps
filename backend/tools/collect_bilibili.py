# -*- coding: utf-8 -*-
"""B 站公开数据采集编排器（受限匿名采样：热门/最新首页 + 楼中楼翻页）。

合规护栏（与 docs/sampling-protocol.md 一致）：
- 仅公开接口；登出等价会话；评论类请求间隔 ≥2.5s，元数据 ≥1.5s。
- code -412/-352 → hard stop（不重试不绕过），状态写 journal，可断点续采。
- 原始 uid 立即 HMAC 匿名化，绝不落盘。
- 采样记录：检索词、排名、采样理由、快照时间。

用法:
  uv run python tools/collect_bilibili.py --study genshin68
  uv run python tools/collect_bilibili.py --study wuwa35
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

from liveops.anonymize import make_anon_fn
from liveops.collector.wbi import WbiSigner
from liveops.schema import CommunityPost, ContentItem, StudyConfig

UTC = timezone.utc
OUT_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*", "Accept-Language": "zh-CN,zh;q=0.9",
    "Origin": "https://www.bilibili.com",
    "sec-ch-ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
    "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"',
    "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-site",
}
RISK_CODES = {-412, -352, -411, 9, -799}

STUDIES = {
    "genshin68": {
        "study_id": "genshin-6.8", "game": "genshin", "version_label": "6.8",
        "t0": date(2026, 7, 1),
        "official_names": {"原神", "米哈游原神"},
        "terms": {
            "official": ["原神6.8 PV", "原神 6.8 前瞻"],
            "guide": ["原神6.8 攻略", "原神6.8 深渊 阵容", "原神 桑多涅 测评"],
            "review": ["原神6.8 体验", "原神6.8 评价"],
            "fanwork": ["原神6.8 二创", "桑多涅 MMD"],
            "controversy": ["原神6.8 卡池", "原神6.8 节奏", "原神6.8 退坑"],
        },
    },
    "wuwa35": {
        "study_id": "wuthering-3.5", "game": "wuthering_waves", "version_label": "3.5",
        "t0": date(2026, 7, 10),
        "official_names": {"鸣潮", "库洛游戏", "库街区"},
        "terms": {
            "official": ["鸣潮3.5 PV", "鸣潮 3.5 前瞻"],
            "guide": ["鸣潮3.5 攻略", "鸣潮3.5 阵容", "鸣潮 3.5 武器"],
            "review": ["鸣潮3.5 体验", "鸣潮3.5 评价"],
            "fanwork": ["鸣潮3.5 二创", "鸣潮3.5 手书"],
            "controversy": ["鸣潮3.5 卡池", "鸣潮3.5 节奏", "鸣潮3.5 争议"],
        },
    },
}


class HardStop(Exception):
    pass


class Collector:
    def __init__(self, cfg: dict, out_dir: Path, comment_interval=2.6, meta_interval=1.6,
                 max_requests=2000):
        self.cfg = cfg
        self.out = out_dir
        self.out.mkdir(parents=True, exist_ok=True)
        self.comment_interval = comment_interval
        self.meta_interval = meta_interval
        self.max_requests = max_requests
        self.requests = 0
        self.last_comment_t = 0.0
        self.last_meta_t = 0.0
        self.client = httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True)
        self._boot()
        self.signer = WbiSigner.from_nav(
            self._get("https://api.bilibili.com/x/web-interface/nav", risk=True))
        self.anon_fn = make_anon_fn(cfg["study_id"])
        self.journal_path = self.out / "search_journal.jsonl"
        self.state = self._load_state()

    # ---------- 基础 ----------
    def _boot(self):
        self.client.get("https://www.bilibili.com/")
        spi = self.client.get("https://api.bilibili.com/x/frontend/finger/spi").json()["data"]
        self.client.cookies.set("buvid3", spi["b_3"], domain=".bilibili.com")
        self.client.cookies.set("buvid4", spi["b_4"], domain=".bilibili.com")

    def _get(self, url: str, *, params=None, risk=False, kind="meta", referer=None):
        interval = self.comment_interval if kind == "comment" else self.meta_interval
        last = self.last_comment_t if kind == "comment" else self.last_meta_t
        wait = interval - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
        self.requests += 1
        if self.requests > self.max_requests:
            raise HardStop("会话请求上限")
        headers = {**HEADERS}
        if referer:
            headers["Referer"] = referer
        r = self.client.get(url, params=params, headers=headers)
        if r.status_code == 412 or r.status_code == 403:
            raise HardStop(f"HTTP {r.status_code} 风控拦截")
        try:
            d = r.json()
        except Exception:
            raise HardStop(f"非 JSON 响应（疑似风控页）status={r.status_code}")
        if kind == "comment":
            self.last_comment_t = time.monotonic()
        else:
            self.last_meta_t = time.monotonic()
        if risk and d.get("code") in RISK_CODES:
            raise HardStop(f"code={d.get('code')} 风控信号")
        return d

    def _load_state(self) -> dict:
        p = self.out / "collect_state.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return {"phase": "search", "selected": [], "post_ids": [], "video_done": [],
                "videos": [], "requests": 0}

    def save_state(self):
        self.state["requests"] = self.requests
        (self.out / "collect_state.json").write_text(
            json.dumps(self.state, ensure_ascii=False, indent=1), encoding="utf-8")

    def journal(self, entry: dict):
        entry["at"] = datetime.now(UTC).isoformat()
        with open(self.journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ---------- 阶段 1：搜索与选片 ----------
    def search_and_select(self, per_category=10, pages_per_term=2):
        cfg = self.cfg
        t0 = cfg["t0"]
        win_lo = datetime.combine(t0, datetime.min.time(), tzinfo=UTC)
        from datetime import timedelta
        win_lo = win_lo - timedelta(days=10)
        win_hi = datetime.combine(t0, datetime.min.time(), tzinfo=UTC) + timedelta(days=40)
        candidates: dict[str, list[dict]] = {}
        for cat, terms in cfg["terms"].items():
            got: list[dict] = []
            seen = set()
            for term in terms:
                if len(got) >= per_category * 2:
                    break
                for page in range(1, pages_per_term + 1):
                    d = self._get("https://api.bilibili.com/x/web-interface/search/type",
                                  params={"search_type": "video", "keyword": term, "page": page},
                                  referer="https://search.bilibili.com/")
                    self.journal({"kind": "search", "term": term, "page": page,
                                  "code": d.get("code")})
                    if d.get("code") != 0:
                        break
                    for r in (d.get("data") or {}).get("result") or []:
                        if r.get("type") != "video":
                            continue
                        bvid = r.get("bvid", "")
                        if not bvid or bvid in seen:
                            continue
                        seen.add(bvid)
                        pub = datetime.fromtimestamp(r.get("pubdate", 0), tz=UTC)
                        if not (win_lo <= pub <= win_hi):
                            continue
                        is_official = (r.get("author") in cfg["official_names"]
                                       or (r.get("official_verify") or {}).get("type") == 1)
                        got.append({"bvid": bvid,
                                    "title": self._strip(r.get("title", "")),
                                    "author": r.get("author", ""), "is_official": is_official,
                                    "pubdate": pub.isoformat(),
                                    "play": int(r.get("play", 0) or 0),
                                    "term": term, "rank": len(got) + 1})
            got.sort(key=lambda x: -x["play"])
            candidates[cat] = got
        # 选片：official 类要求 is_official；其余排除官方号（避免重复占额）
        selected = []
        for cat, got in candidates.items():
            pool = [g for g in got if (g["is_official"] if cat == "official" else not g["is_official"])]
            if len(pool) < 6:  # 官方号不足时放宽（记录）
                self.journal({"kind": "relax", "category": cat, "reason": "候选不足放宽条件"})
                pool = got
            take = pool[:per_category]
            for g in take:
                g["category"] = cat
                g["sampling_reason"] = (f"类别[{cat}] 检索词『{g['term']}』结果，"
                                        f"播放 {g['play']}，发布 {g['pubdate'][:10]}")
                selected.append(g)
        self.state["selected"] = selected
        self.state["phase"] = "collect"
        self.save_state()
        return selected

    @staticmethod
    def _strip(t: str) -> str:
        import re
        return re.sub(r"<[^>]+>", "", t or "").strip()

    # ---------- 阶段 2：元数据 + 评论 ----------
    def collect(self, target_per_video=110, sub_pages_max=8, per_video_cap=400):
        done = set(self.state["video_done"])
        posts_fh = open(self.out / "posts.jsonl", "a", encoding="utf-8")
        videos_fh = open(self.out / "videos.jsonl", "a", encoding="utf-8")
        new_posts = 0
        for sel in self.state["selected"]:
            bvid = sel["bvid"]
            if bvid in done:
                continue
            try:
                meta = self._get("https://api.bilibili.com/x/web-interface/view",
                                 params={"bvid": bvid}, risk=True,
                                 referer=f"https://www.bilibili.com/video/{bvid}/")
            except HardStop:
                posts_fh.close(); videos_fh.close()
                self.save_state()
                raise
            if meta.get("code") != 0:
                self.journal({"kind": "meta_fail", "bvid": bvid, "code": meta.get("code")})
                done.add(bvid); self.state["video_done"] = list(done); self.save_state()
                continue
            v = meta["data"]
            aid = v["aid"]
            video = {
                "video_id": bvid, "title": v.get("title", ""), 
                "url": f"https://www.bilibili.com/video/{bvid}/",
                "published_at": datetime.fromtimestamp(v.get("pubdate", 0), tz=UTC).isoformat(),
                "category": sel["category"],
                "author_type": "official" if sel["is_official"] and sel["category"] == "official" else "ugc",
                "stats_snapshot": {
                    "view": v["stat"].get("view", 0), "like": v["stat"].get("like", 0),
                    "coin": v["stat"].get("coin", 0), "favorite": v["stat"].get("favorite", 0),
                    "share": v["stat"].get("share", 0), "comment": v["stat"].get("reply", 0),
                    "snapshot_at": datetime.now(UTC).isoformat(),
                },
                "search_term_used": sel["term"], "search_rank": sel.get("rank", 0),
                "sampling_reason": sel["sampling_reason"],
            }
            videos_fh.write(json.dumps(video, ensure_ascii=False) + "\n")
            videos_fh.flush()
            self.journal({"kind": "meta", "bvid": bvid, "title": video["title"][:40],
                          "reply_total": video["stats_snapshot"].get("comment", 0)})

            # 评论：热门 + 最新 + 楼中楼
            known = set(self.state["post_ids"])
            collected: list[dict] = []
            roots_meta: list[dict] = []
            for mode in (3, 2):
                try:
                    d = self._get("https://api.bilibili.com/x/v2/reply/wbi/main",
                                  params=self.signer.sign({"oid": aid, "type": 1, "mode": mode,
                                                           "next": 0, "ps": 20}),
                                  risk=True, kind="comment",
                                  referer=video["url"])
                except HardStop:
                    posts_fh.close(); videos_fh.close(); self.save_state(); raise
                data = d.get("data") or {}
                roots_meta.append({"mode": mode, "replies": data.get("replies") or []})
                for r in (data.get("replies") or []):
                    self._append_root(r, bvid, video["url"], collected, known)
                top = (data.get("top") or {}).get("upper")
                if top:
                    self._append_root(top, bvid, video["url"], collected, known)
            # 楼中楼
            for batch in roots_meta:
                for r in batch["replies"]:
                    rcount = int(r.get("rcount", 0) or 0)
                    if rcount < 3 or len(collected) >= target_per_video:
                        continue
                    root_rpid = r["rpid"]
                    for pn in range(1, sub_pages_max + 1):
                        if len(collected) >= min(target_per_video, per_video_cap):
                            break
                        try:
                            d = self._get("https://api.bilibili.com/x/v2/reply/reply",
                                          params=self.signer.sign({"oid": aid, "type": 1,
                                                                   "root": root_rpid,
                                                                   "pn": pn, "ps": 20}),
                                          risk=True, kind="comment", referer=video["url"])
                        except HardStop:
                            posts_fh.close(); videos_fh.close(); self.save_state(); raise
                        subs = (d.get("data") or {}).get("replies") or []
                        for s in subs:
                            self._append_sub(s, bvid, video["url"], collected, known,
                                             parent=str(root_rpid))
                        if len(subs) < 20:
                            break
            for p in collected:
                posts_fh.write(json.dumps(p, ensure_ascii=False) + "\n")
                self.state["post_ids"].append(p["post_id"])
            new_posts += len(collected)
            posts_fh.flush()
            self.journal({"kind": "video_done", "bvid": bvid, "comments": len(collected)})
            done.add(bvid)
            self.state["video_done"] = list(done)
            self.save_state()
        posts_fh.close()
        videos_fh.close()
        return new_posts

    def _post(self, r: dict, bvid: str, url: str, parent: str | None) -> dict | None:
        msg = ((r.get("content") or {}).get("message") or "").strip()
        if not msg:
            return None
        return {
            "post_id": str(r.get("rpid", "")),
            "video_id": bvid,
            "parent_id": parent,
            "text": msg,
            "published_at": datetime.fromtimestamp(int(r.get("ctime", 0) or 0), tz=UTC).isoformat(),
            "likes": int(r.get("like", 0) or 0),
            "reply_count": int(r.get("rcount", 0) or 0),
            "anon_user_id": self.anon_fn(str((r.get("member") or {}).get("mid", ""))),
            "collected_at": datetime.now(UTC).isoformat(),
            "source_url": url,
            "synthetic": False,
        }

    def _append_root(self, r, bvid, url, collected, known):
        p = self._post(r, bvid, url, None)
        if p and p["post_id"] and p["post_id"] not in known:
            collected.append(p)
            known.add(p["post_id"])

    def _append_sub(self, s, bvid, url, collected, known, parent):
        p = self._post(s, bvid, url, parent)
        if p and p["post_id"] and p["post_id"] not in known:
            collected.append(p)
            known.add(p["post_id"])


def expand_selection(col: "Collector", per_category=14) -> int:
    """补充选片：跨类去重、跳过已完成视频，目标 ~55-60 唯一视频。"""
    done = set(col.state["video_done"])
    old = {s["bvid"]: s for s in col.state["selected"]}
    new_sel = col.search_and_select(per_category=per_category)
    merged: dict[str, dict] = dict(old)
    added = 0
    for s in new_sel:
        if s["bvid"] not in merged:
            merged[s["bvid"]] = s
            added += 1
    # 去掉已完成
    todo = [s for s in merged.values() if s["bvid"] not in done]
    col.state["selected"] = todo + [s for s in merged.values() if s["bvid"] in done]
    col.save_state()
    return added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--study", choices=list(STUDIES), required=True)
    ap.add_argument("--max-requests", type=int, default=2000)
    ap.add_argument("--expand", action="store_true", help="补充选片并采集新视频")
    args = ap.parse_args()
    cfg = STUDIES[args.study]
    out = OUT_ROOT / cfg["study_id"]
    col = Collector(cfg, out, max_requests=args.max_requests)
    print(f"[collect] study={cfg['study_id']} out={out} phase={col.state['phase']}")
    try:
        if args.expand:
            added = expand_selection(col)
            print(f"[expand] 新增候选视频 {added}")
        if col.state["phase"] == "search":
            sel = col.search_and_select()
            print(f"[select] {len(sel)} videos: " +
                  ", ".join(f"{c}={sum(1 for s in sel if s['category']==c)}"
                            for c in ("official","guide","review","fanwork","controversy")))
        n = col.collect()
        print(f"[collect] 新增评论 {n}，累计 {len(col.state['post_ids'])}，请求 {col.requests}")
    except HardStop as e:
        print(f"[HARD STOP] {e} —— 已保存断点（{len(col.state['video_done'])} 视频完成，"
              f"{len(col.state['post_ids'])} 评论）。按协议不重试，可续跑或转导入模式。")
        col.save_state()
    print(f"[done] phase={col.state['phase']}")


if __name__ == "__main__":
    main()
