"""匿名化测试：HMAC 不可逆、脱敏、泄漏扫描、公开导出断言。"""

import pytest

from liveops.anonymize import (
    LeakError,
    anon_id,
    assert_no_pii,
    build_public_export,
    get_or_create_salt,
    make_anon_fn,
    mask_text,
    scan_for_leaks,
)


@pytest.fixture
def salt(tmp_path, monkeypatch):
    import liveops.config as cfg
    monkeypatch.setattr(cfg, "SECRETS_DIR", tmp_path)
    return get_or_create_salt("study-x")


class TestAnonId:
    def test_deterministic_and_truncated(self, salt):
        a = anon_id(salt, "123456789")
        b = anon_id(salt, "123456789")
        assert a == b and len(a) == 16

    def test_irreversible_format(self, salt):
        # 输出不含原始输入，且无法从 16 位 hex 反推 uid（结构断言）
        out = anon_id(salt, "987654321")
        assert "987654321" not in out
        int(out, 16)  # 合法 hex

    def test_different_salt_different_id(self, tmp_path, monkeypatch):
        import liveops.config as cfg
        monkeypatch.setattr(cfg, "SECRETS_DIR", tmp_path)
        s1 = get_or_create_salt("study-a")
        s2 = get_or_create_salt("study-b")
        assert anon_id(s1, "42") != anon_id(s2, "42")

    def test_salt_persisted(self, salt, tmp_path):
        again = get_or_create_salt("study-x")
        assert again == salt


class TestMaskText:
    def test_mention_masked(self):
        assert mask_text("@某用户 你说得对") == "@*** 你说得对"

    def test_qq_masked(self):
        assert "123456" not in mask_text("加我QQ:123456")

    def test_uid_masked(self):
        assert mask_text("UID: 123456789 你发现了") == "UID:*** 你发现了"

    def test_normal_text_untouched(self):
        s = "这版本剧情真不错，强烈推荐！"
        assert mask_text(s) == s


class TestLeakScan:
    def test_forbidden_key_detected(self):
        leaks = scan_for_leaks({"uname": "张三", "ok": 1})
        assert any("uname" in l for l in leaks)

    def test_nested_detected(self):
        leaks = scan_for_leaks({"data": [{"mid": 123}]})
        assert leaks

    def test_clean_passes(self):
        assert scan_for_leaks({"text": "正常评论", "anon_user_id": "abc"}) == []

    def test_text_uid_detected(self):
        assert scan_for_leaks({"text": "看 UID:12345678"}) 

    def test_homepage_link_detected(self):
        assert scan_for_leaks({"url": "https://space.bilibili.com/123456"})

    def test_assert_no_pii_raises(self):
        with pytest.raises(LeakError):
            assert_no_pii({"avatar": "http://x/y.jpg"})

    def test_assert_no_pii_passes_clean(self):
        assert_no_pii({"text": "干净的评论", "likes": 3})


class TestPublicExport:
    def _posts(self):
        return [{
            "post_id": "p1", "video_id": "BV1", "parent_id": None,
            "text": "@某人 说得对，UID: 987654321", "published_at": "2026-07-02T00:00:00+00:00",
            "likes": 5, "reply_count": 0, "anon_user_id": "abcd1234abcd1234",
            "dedup_group": "dg-1", "flags": [], "synthetic": False,
            "source_url": "https://www.bilibili.com/video/BV1",
        }]

    def _videos(self):
        return [{
            "video_id": "BV1", "title": "标题", "url": "https://www.bilibili.com/video/BV1",
            "published_at": "2026-06-25T00:00:00+00:00", "category": "review",
            "author_type": "ugc", "stats_snapshot": {"view": 1, "like": 2, "coin": 0, "favorite": 0, "share": 0, "comment": 3},
        }]

    def test_export_masks_text(self):
        export = build_public_export(self._posts(), self._videos())
        assert "@***" in export["posts"][0]["text"]
        assert "987654321" not in export["posts"][0]["text"]

    def test_export_has_no_user_fields(self):
        export = build_public_export(self._posts(), self._videos())
        assert not scan_for_leaks(export)

    def test_export_whitelist_strips_dirty_fields(self):
        posts = self._posts()
        posts[0]["uname"] = "泄漏"  # 模拟上游混入
        posts[0]["mid"] = 12345
        export = build_public_export(posts, self._videos())
        # 白名单投影：未知字段不进入公开导出
        assert "uname" not in export["posts"][0]
        assert not scan_for_leaks(export)

    def test_text_leak_still_raises(self):
        # 白名单内的 text 字段若含未脱敏 PII（绕过 mask 的路径）→ 扫描兜底
        from liveops.anonymize import assert_no_pii
        with pytest.raises(LeakError):
            assert_no_pii({"text": "加我QQ:1234567890"})
