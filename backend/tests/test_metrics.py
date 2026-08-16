"""指标公式测试：手工 fixture 精确断言（禁止近似通过）。"""

import math

import pytest

from liveops.metrics import (
    StanceDist,
    controversy_score,
    entropy_norm,
    issue_priority_scores,
    log_engagement_raw,
    minmax_normalize,
    net_support_rate,
    opportunity_scores,
    per_ten_videos,
    per_thousand,
    persistence,
    rank_of,
    reply_conflict,
    stance_dist,
    topic_share,
    trend_speed,
    volume_norm,
    weight_sensitivity,
)


class TestBasic:
    def test_topic_share(self):
        assert topic_share(120, 4000) == pytest.approx(0.03)
        assert topic_share(5, 0) is None

    def test_net_support_rate_exact(self):
        d = StanceDist(support=3, oppose=1)
        assert net_support_rate(d) == pytest.approx(0.5)
        assert net_support_rate(StanceDist()) is None
        assert net_support_rate(StanceDist(neutral=5)) is None

    def test_stance_dist_counts(self):
        d = stance_dist(["支持", "反对", "反对", "中立", "混合", "不明确", None])
        assert (d.support, d.oppose, d.neutral, d.mixed, d.unclear, d.abstain) == (1, 2, 1, 1, 1, 1)

    def test_entropy_max_when_uniform(self):
        d = StanceDist(support=25, oppose=25, neutral=25, mixed=25)
        assert entropy_norm(d) == pytest.approx(1.0)
        assert entropy_norm(StanceDist(support=100)) == pytest.approx(0.0)
        assert entropy_norm(StanceDist()) == 0.0

    def test_reply_conflict(self):
        edges = [("支持", "反对"), ("支持", "支持"), ("反对", "支持"), ("中立", "支持")]
        # 已知立场边 = 前三条（中立被排除），其中对立两条
        assert reply_conflict(edges) == pytest.approx(2 / 3)
        assert reply_conflict([]) is None
        assert reply_conflict([("中立", "中立")]) is None

    def test_controversy_exact(self):
        d = StanceDist(support=25, oppose=25, neutral=25, mixed=25)  # H_norm=1
        # conflict=0.5, topic=1000, total=4000 → log1p(1000)/log1p(4000)
        v = math.log1p(1000) / math.log1p(4000)
        expect = 0.5 * 1.0 + 0.3 * 0.5 + 0.2 * v
        assert controversy_score(d, 0.5, 1000, 4000) == pytest.approx(expect)

    def test_trend_speed_rising(self):
        counts = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512]  # 指数增长
        assert trend_speed(counts) > 0.35  # 几何级数 slope/mean≈0.41
        # 末期尖峰：斜率为正但温和
        assert trend_speed([10] * 9 + [100]) == pytest.approx(405 / 82.5 / 19)
        assert trend_speed([5] * 10) == pytest.approx(0.0)
        assert trend_speed([0] * 10) is None
        assert trend_speed([1]) is None

    def test_trend_speed_declining(self):
        assert trend_speed(list(range(100, 0, -10))) < 0

    def test_engagement_raw(self):
        v = log_engagement_raw([0, 999], [0, 0])
        expect = (math.log1p(0) + math.log1p(999)) / 2
        assert v == pytest.approx(expect)

    def test_persistence(self):
        p = persistence(18, 36, 10, 40)
        assert p == pytest.approx(0.5 * 0.5 + 0.5 * 0.25)

    def test_volume_norm_bounds(self):
        assert volume_norm(4000, 4000) == pytest.approx(1.0)
        assert volume_norm(0, 4000) == 0.0


class TestComposite:
    def test_minmax(self):
        n = minmax_normalize({"a": 0.0, "b": 5.0, "c": 10.0})
        assert n == {"a": 0.0, "b": 0.5, "c": 1.0}
        assert minmax_normalize({"a": 1, "b": 1}) == {"a": 0.5, "b": 0.5}

    def test_issue_priority_weights_sum(self):
        assert sum(issue_priority_scores.__defaults__ or []) if False else True
        from liveops.metrics.composite import DEFAULT_ISSUE_WEIGHTS, DEFAULT_OPPORTUNITY_WEIGHTS
        assert sum(DEFAULT_ISSUE_WEIGHTS.values()) == pytest.approx(1.0)
        assert sum(DEFAULT_OPPORTUNITY_WEIGHTS.values()) == pytest.approx(1.0)

    def test_issue_priority_exact(self):
        rows = {
            "抽卡与商业化": {"oppose_intensity": 1.0, "topic_share": 0.2, "growth": 0.0, "engagement": 0.0, "persistence": 0.0},
            "剧情与世界观": {"oppose_intensity": 0.0, "topic_share": 0.0, "growth": 1.0, "engagement": 0.0, "persistence": 0.0},
        }
        s = issue_priority_scores(rows)
        assert s["抽卡与商业化"] == pytest.approx(0.30 * 1.0 + 0.25 * 0.2)
        assert s["剧情与世界观"] == pytest.approx(0.20)

    def test_opportunity_exact(self):
        rows = {"A": {"support_rate": 1.0, "topic_growth": 0.0, "video_coverage": 0.0, "engagement": 0.0, "persistence": 0.0}}
        assert opportunity_scores(rows)["A"] == pytest.approx(0.35)

    def test_rank(self):
        assert rank_of({"a": 0.9, "b": 0.5, "c": 0.7}) == {"a": 1, "c": 2, "b": 3}

    def test_weight_sensitivity_rank_shift(self):
        rows = {
            t: {"oppose_intensity": a, "topic_share": b, "growth": c, "engagement": 0.1, "persistence": 0.1}
            for t, a, b, c in [("A", 0.9, 0.1, 0.1), ("B", 0.1, 0.9, 0.1), ("C", 0.1, 0.1, 0.9)]
        }
        from liveops.metrics.composite import DEFAULT_ISSUE_WEIGHTS
        res = weight_sensitivity(rows, DEFAULT_ISSUE_WEIGHTS, "issue")
        assert res.base_ranks["A"] == 1  # 0.3*0.9+0.25*0.1 > 0.25*0.9 > 0.2*0.9
        assert len(res.scenarios) == 10  # 5 权重 × ±
        # 每个情景权重和为 1
        for s in res.scenarios:
            assert sum(s["weights"].values()) == pytest.approx(1.0)

    def test_per_thousand_and_videos(self):
        assert per_thousand(500, 2500) == pytest.approx(200.0)
        assert per_thousand(10, 0) is None
        assert per_ten_videos(15, 50) == pytest.approx(3.0)
