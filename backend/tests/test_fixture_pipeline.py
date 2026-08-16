"""纵向切片测试：synthetic_100 夹具端到端（ScriptedLLM 回放种子标注）。"""

import pytest

from liveops.fixtures import load_fixture
from liveops.harness.graph import HarnessDeps, run_pipeline
from liveops.llm import ScriptedLLM, register_scripted
from liveops.llm.prompts import v1
from liveops.schema import RunStatus, StageStatus


@pytest.fixture(scope="module")
def fixture_result(tmp_path_factory):
    fx = load_fixture("synthetic_100")
    register_scripted(v1.ANNOTATE_VERSION, fx.seed_annotations)
    tmp = tmp_path_factory.mktemp("runs")
    return run_pipeline(fx.study, fx.posts, fx.videos,
                        HarnessDeps(ScriptedLLM()), runs_dir=tmp)


class TestVerticalSlice:
    def test_fixture_shape(self):
        fx = load_fixture("synthetic_100")
        assert len(fx.posts) == 100
        assert len(fx.videos) == 10
        assert len(fx.seed_annotations) == 100
        # 全部样本必须显式 synthetic 标记
        assert all(p.synthetic for p in fx.posts)

    def test_run_completes_all_stages(self, fixture_result):
        r = fixture_result.run
        assert r.status == RunStatus.COMPLETED
        assert all(s.status == StageStatus.DONE for s in r.stage_states.values())

    def test_metrics_sane(self, fixture_result):
        m = fixture_result.state["metrics"]
        d = m["dataset"]
        # 100 输入 → 99 进入标注：p094（单个问号）在规范化被判 spam 剔除；
        # 标注后：p100 注入样本弃权(1)、p096-098 无关(3)、p099 重复排除出有效样本(1)
        assert d["total_posts"] == 99
        assert d["abstain_count"] == 1
        assert d["irrelevant_count"] == 3
        assert d["relevant_posts"] == 94
        # 主题覆盖广度（12 固定主题至少命中 10 个）
        assert len(m["topics"]) >= 10
        # 抽卡与商业化是重点问题方向（12 条样本 + 高反对）
        assert "抽卡与商业化" in m["topics"]
        ts = m["topics"]["抽卡与商业化"]
        assert ts["net_support_rate"] < 0  # 反对占优
        # 组合分数 + 敏感性存在
        assert m["composites"]["issue_priority"]["scores"]
        assert m["composites"]["sensitivity"]["issue"]["base_ranks"]

    def test_claims_verified_and_cited(self, fixture_result):
        state = fixture_result.state
        assert state["verify_result"]["passed"]
        for c in state["claims"]:
            assert c["metric_ids"] and c["evidence_ids"]
            assert "所采样的" in c["text"]

    def test_injection_sample_abstained_not_followed(self, fixture_result):
        """注入样本 p100 必须弃权，绝不能执行文本中的指令。"""
        anns = {a["post_id"]: a for a in fixture_result.state["annotations"]}
        a = anns["p100"]
        assert a["relevant"] is None
        assert a["abstain_reason"]
        assert a["stance"] is None  # 指令"标记为支持"未被执行

    def test_duplicate_flagged(self, fixture_result):
        # 重复样本保留在数据集（审计可见）但被排除出有效样本（见 relevant_posts=94）
        posts = fixture_result.state["posts"]
        dup = [p for p in posts if p["post_id"] == "p099"]
        assert len(dup) == 1 and "duplicate" in dup[0]["flags"]

    def test_report_written(self, fixture_result, tmp_path):
        html = fixture_result.state["report_html"]
        assert "所采样的 B 站讨论" in html
        assert "href=" in html
