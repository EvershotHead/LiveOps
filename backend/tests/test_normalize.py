"""规范化测试：清洗、SimHash 去重、垃圾标记、时间窗、有效样本。"""

from datetime import date, datetime, timedelta, timezone

from liveops.normalize import (
    NormalizeReport,
    chinese_ratio,
    clean_text,
    detect_flags,
    effective_posts,
    exact_hash,
    hamming,
    normalize_posts,
    simhash64,
)
from liveops.schema import CommunityPost, PostFlag, StudyConfig

UTC = timezone.utc


def study():
    return StudyConfig(
        study_id="s", game="genshin", version_label="6.8", t0_date=date(2026, 7, 1)
    )


def post(pid, text, day, likes=0):
    return CommunityPost(
        post_id=pid, video_id="BV1", text=text,
        published_at=datetime(2026, 7, 1, tzinfo=UTC) + timedelta(days=day),
        likes=likes, anon_user_id="u1", source_url="https://b.example/BV1",
    )


class TestClean:
    def test_strips_control_and_zero_width(self):
        assert clean_text("你\u200b好\x00world") == "你好world"

    def test_collapses_whitespace(self):
        assert clean_text("a   b\t\tc\n\n\n\nd") == "a b c\n\nd"

    def test_keeps_emoji(self):
        assert clean_text("太好了🎉🎉") == "太好了🎉🎉"


class TestFlags:
    def test_lottery(self):
        assert PostFlag.LOTTERY in detect_flags("转发抽三位送小月卡")

    def test_ad(self):
        assert PostFlag.AD in detect_flags("低价代充加微信xxx")

    def test_spam_repeat(self):
        assert PostFlag.SPAM in detect_flags("哈" * 30)

    def test_spam_emoji_only(self):
        assert PostFlag.SPAM in detect_flags("😭")

    def test_normal_not_flagged(self):
        assert detect_flags("这版本剧情真好哭") == []


class TestSimHash:
    def test_identical_text_same_hash(self):
        assert simhash64("深渊太难打了") == simhash64("深渊太难打了")

    def test_fuzzy_duplicate_detection(self):
        from liveops.normalize import _fuzzy_dup
        assert _fuzzy_dup("这版本的地图设计真好，探索感拉满", "这版本的地图设计真不错，探索感拉满")
        assert not _fuzzy_dup("今天天气不错适合出去玩", "深渊十二层满星阵容推荐攻略")

    def test_different_text_large_hamming(self):
        a = simhash64("今天天气不错适合出去玩")
        b = simhash64("深渊十二层满星阵容推荐攻略")
        assert hamming(a, b) > 6


class TestNormalize:
    def test_time_window_filter(self):
        posts = [post("p1", "好", 0), post("p2", "好", -7), post("p3", "好", 28),
                 post("p4", "好", -8), post("p5", "好", 29), post("p6", "好", 100)]
        kept, rep = normalize_posts(posts, study())
        assert rep.dropped_out_of_window == 3
        assert rep.kept == 3

    def test_exact_duplicate_flagged_same_group(self):
        posts = [post("p1", "这版本真好玩", 1), post("p2", "这版本真好玩", 2),
                 post("p3", "这版本真好玩", 3)]
        kept, rep = normalize_posts(posts, study())
        assert rep.duplicates_flagged == 2
        groups = {p.dedup_group for p in kept}
        assert len(groups) == 1
        dups = [p for p in kept if PostFlag.DUPLICATE in p.flags]
        assert len(dups) == 2

    def test_near_duplicate_grouped(self):
        posts = [post("p1", "这版本的地图设计真好探索感拉满", 1),
                 post("p2", "这版本的地图设计真不错探索感拉满", 2)]
        kept, rep = normalize_posts(posts, study())
        assert kept[0].dedup_group == kept[1].dedup_group
        assert PostFlag.DUPLICATE in kept[1].flags

    def test_spam_dropped(self):
        posts = [post("p1", "哈" * 40, 1), post("p2", "正常评论", 1)]
        kept, rep = normalize_posts(posts, study())
        assert rep.dropped_spam == 1
        assert all(p.post_id != "p1" for p in kept)

    def test_lottery_kept_but_flagged(self):
        posts = [post("p1", "关注抽奖送周边啦", 1)]
        kept, _ = normalize_posts(posts, study())
        assert PostFlag.LOTTERY in kept[0].flags

    def test_effective_posts_excludes_noise(self):
        posts = [post("p1", "重复文本啊", 1), post("p2", "重复文本啊", 2),
                 post("p3", "转发抽奖送月卡", 1), post("p4", "正常评论内容", 1)]
        kept, _ = normalize_posts(posts, study())
        eff = effective_posts(kept)
        assert [p.post_id for p in eff] == ["p1", "p4"]

    def test_chinese_ratio(self):
        assert chinese_ratio("全部中文") == 1.0
        assert chinese_ratio("english only") < 0.15

    def test_empty_report_shape(self):
        kept, rep = normalize_posts([], study())
        assert kept == [] and rep.total_in == 0
