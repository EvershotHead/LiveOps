"""采集器测试：限速、硬停不重试、journal 断点、解析容错、配额校验。"""

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from liveops.collector import (
    CollectionJournal,
    CollectionSession,
    CollectorHardStop,
    CollectorLimits,
    TokenBucket,
    check_risk,
    fetch_comments_page,
    fetch_video_meta,
    parse_comment,
    search_videos,
    validate_sample,
)
from liveops.schema import CommunityPost, ContentItem, StudyConfig

UTC = timezone.utc


def fake_reply_payload(n=3, code=0):
    def c(i):
        return {"rpid": 1000 + i, "parent": 0, "ctime": 1751500000 + i,
                "like": 10 * i, "rcount": i,
                "content": {"message": f"第{i}条评论内容"},
                "member": {"mid": 200000 + i, "uname": f"用户{i}"}}
    return {"code": code, "data": {"replies": [c(i) for i in range(n)],
                                   "cursor": {"is_end": n < 3, "next": 2, "all_count": 100}}}


class TestRisk:
    def test_risk_code_hard_stop(self):
        with pytest.raises(CollectorHardStop):
            check_risk({"code": -412})
        with pytest.raises(CollectorHardStop):
            check_risk({"code": 0, "data": {"code": -352}})

    def test_normal_pass(self):
        check_risk({"code": 0, "data": {}})


class TestRateLimit:
    def test_min_interval_enforced(self):
        t = {"now": 0.0}
        sleeps = []
        bucket = TokenBucket(2.5, clock=lambda: t["now"], sleeper=lambda s: sleeps.append(s) or t.__setitem__("now", t["now"] + s))
        assert bucket.acquire() == 0.0
        w = bucket.acquire()
        assert w == pytest.approx(2.5)
        assert sleeps == [pytest.approx(2.5)]

    def test_no_wait_reports_block(self):
        t = {"now": 0.0}
        bucket = TokenBucket(1.0, clock=lambda: t["now"])
        bucket.acquire(wait=False)
        assert bucket.would_block()
        t["now"] += 1.0
        assert not bucket.would_block()


class TestParsers:
    def test_search_parses_videos(self):
        payload = {"code": 0, "data": {"result": [
            {"type": "video", "bvid": "BV1", "title": "<em class=\"keyword\">原神</em>6.8攻略",
             "author": "up主", "mid": 1, "pubdate": 1751000000, "play": 5000, "review": 200},
            {"type": "article", "bvid": "BV2", "title": "无关"},
        ]}}
        got = search_videos(lambda url: payload, "原神6.8")
        assert len(got) == 1
        assert got[0]["title"] == "原神6.8攻略"
        assert got[0]["rank"] == 1

    def test_search_risk_raises(self):
        with pytest.raises(CollectorHardStop):
            search_videos(lambda url: {"code": -352, "data": {}}, "原神")

    def test_meta_parses(self):
        payload = {"code": 0, "data": {
            "bvid": "BV1", "aid": 111, "title": "标题", "pubdate": 1751000000,
            "owner": {"mid": 9, "name": "官号"},
            "stat": {"view": 100, "like": 10, "coin": 5, "favorite": 4, "share": 3, "reply": 2},
        }}
        m = fetch_video_meta(lambda url: payload, "BV1")
        assert m["stat"]["view"] == 100 and m["owner_name"] == "官号"

    def test_comment_page_parses(self):
        res = fetch_comments_page(lambda url: fake_reply_payload(3), 111, mode=3, next_page=1)
        assert len(res["roots"]) == 3
        assert res["roots"][0].post_id == "1000"
        assert res["roots"][0].parent_id is None

    def test_comment_structural_drift_returns_empty(self):
        res = fetch_comments_page(lambda url: {"code": 0, "data": None}, 111)
        assert res["roots"] == [] and res["is_end"]

    def test_parse_comment_skips_empty(self):
        assert parse_comment([{"rpid": 1, "content": {"message": "  "}}]) == []

    def test_sub_reply_parent(self):
        got = parse_comment([{"rpid": 5, "parent": 1000, "ctime": 1, "like": 0,
                              "content": {"message": "楼中楼"}, "member": {"mid": 3}}])
        assert got[0].parent_id == "1000"


class TestJournalResume:
    def test_pages_not_repeated(self, tmp_path):
        j = CollectionJournal(tmp_path / "j.jsonl")
        j.log("comment", url="u", page=1, items=2, video_id="BV1", mode="mode3",
              post_ids=["a", "b"])
        j.close()
        # 重启后同页跳过
        j2 = CollectionJournal(tmp_path / "j.jsonl")
        assert j2.has_page("BV1", "mode3", 1)
        assert not j2.has_page("BV1", "mode3", 2)
        assert j2.post_ids == {"a", "b"}

    def test_half_line_ignored(self, tmp_path):
        p = tmp_path / "j.jsonl"
        p.write_text('{"at":"t","kind":"info","url":"","page":0,"items":0,"detail":{}}\n'
                     '{"at":"t","kind":"comment"  # 半行崩溃残留\n', encoding="utf-8")
        j = CollectionJournal(p)
        assert not j.has_page("BV1", "mode3", 1)


class TestSession:
    def _session(self, tmp_path, payloads):
        calls = []
        j = CollectionJournal(tmp_path / "j.jsonl")
        limits = CollectorLimits(comment_interval_s=0.0, meta_interval_s=0.0,
                                 max_requests_per_session=5)
        def fetch(url):
            calls.append(url)
            return payloads(url)
        return CollectionSession(fetch=fetch, journal=j, limits=limits), calls, j

    def test_request_cap_hard_stop(self, tmp_path):
        s, calls, j = self._session(tmp_path, lambda u: fake_reply_payload(1))
        for _ in range(5):
            s.get_comment_page(1, "BV1", 3, page=_ + 1)
        with pytest.raises(CollectorHardStop):
            s.get_comment_page(1, "BV1", 3, page=99)

    def test_risk_no_retry(self, tmp_path):
        state = {"risk": False}
        def payload(url):
            if state["risk"]:
                return {"code": -412}
            return fake_reply_payload(1)
        s, calls, j = self._session(tmp_path, payload)
        s.get_comment_page(1, "BV1", 3, page=1)
        n_before = len(calls)
        state["risk"] = True
        with pytest.raises(CollectorHardStop):
            s.get_comment_page(1, "BV1", 3, page=2)
        # 硬停后不再发出任何请求（不重试）
        n_after = len(calls)
        with pytest.raises(CollectorHardStop):
            s.get_comment_page(1, "BV1", 3, page=3)
        assert len(calls) == n_after == n_before + 1
        assert any(e.kind == "hard_stop" for e in j.entries)

    def test_resumed_page_skipped(self, tmp_path):
        s, calls, j = self._session(tmp_path, lambda u: fake_reply_payload(1))
        s.get_comment_page(1, "BV1", 3, page=1)
        n = len(calls)
        res = s.get_comment_page(1, "BV1", 3, page=1)  # journal 已记录 → 跳过
        assert res.get("skip") and len(calls) == n


def make_study(**kw):
    d = dict(study_id="s", game="genshin", version_label="6.8", t0_date=date(2026, 7, 1))
    d.update(kw)
    return StudyConfig(**d)


def make_videos(n_per_cat=8):
    out = []
    cats = ["official", "guide", "review", "fanwork", "controversy"]
    for ci, cat in enumerate(cats):
        for i in range(n_per_cat):
            vid = f"BV{ci}{i}"
            out.append(ContentItem(video_id=vid, title=vid, url=f"https://b/{vid}",
                                   published_at=datetime(2026, 6, 25, tzinfo=UTC),
                                   category=cat))
    return out


def make_posts(videos, per_video=100, day=5):
    out = []
    for k, v in enumerate(videos):
        for i in range(per_video):
            out.append(CommunityPost(
                post_id=f"p{k}-{i}", video_id=v.video_id, text=f"评论{k}-{i}",
                published_at=datetime(2026, 7, 1, tzinfo=UTC) + timedelta(days=day),
                anon_user_id=f"u{k}-{i % per_video}", source_url=v.url))
    return out


class TestQuota:
    def test_valid_sample_passes(self):
        vids, study = make_videos(8), make_study()
        posts = make_posts(vids, 100)
        rep = validate_sample(posts, vids, study)
        assert rep.ok, rep.summary()

    def test_single_video_over_share_fails(self):
        vids, study = make_videos(8), make_study()
        posts = make_posts(vids, 10)
        big = [CommunityPost(post_id=f"big{i}", video_id="BV00", text="x",
                             published_at=datetime(2026, 7, 2, tzinfo=UTC),
                             anon_user_id=f"u{i}", source_url="u") for i in range(500)]
        rep = validate_sample(posts + big, vids, study)
        assert not rep.ok
        assert any(c["name"] == "单视频上限" and not c["passed"] for c in rep.checks)

    def test_category_coverage_fails(self):
        vids = make_videos(8)
        vids = [v for v in vids if v.category.value != "fanwork"]
        posts = make_posts(vids, 100)
        rep = validate_sample(posts, vids, make_study())
        assert not rep.ok

    def test_comment_quota_range(self):
        vids = make_videos(8)
        posts = make_posts(vids, 2)  # 80 条 < 4000
        rep = validate_sample(posts, vids, make_study())
        assert not rep.ok

    def test_window_purity(self):
        vids, study = make_videos(8), make_study()
        posts = make_posts(vids, 100, day=3)
        outside = [CommunityPost(post_id=f"o{i}", video_id="BV00", text="x",
                                 published_at=datetime(2026, 9, 1, tzinfo=UTC),
                                 anon_user_id=f"u{i}", source_url="u") for i in range(400)]
        rep = validate_sample(posts + outside, vids, study)
        assert any(c["name"] == "时间窗纯度" and not c["passed"] for c in rep.checks)
