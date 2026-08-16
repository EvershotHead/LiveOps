"""Harness 测试：端到端管道、断点续跑、单任务锁、复核路由、结论验证、报告渲染。"""

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from liveops.harness import STAGES, RunLock, RunLockError
from liveops.harness.checkpoints import CheckpointStore, output_hash
from liveops.harness.graph import HarnessDeps, build_langgraph, run_pipeline
from liveops.harness.nodes import build_claims, route_review
from liveops.llm import ScriptedLLM, register_scripted
from liveops.report.verify import Claim, verify_claims
from liveops.report.render import render_report_html
from liveops.schema import (
    Annotation,
    AnnotateStage,
    CommunityPost,
    ContentItem,
    RunStatus,
    StageStatus,
    StudyConfig,
)

UTC = timezone.utc


def make_study():
    return StudyConfig(
        study_id="fixture-test", game="genshin", version_label="6.8",
        t0_date=date(2026, 7, 1),
    )


def make_video(vid, cat="review"):
    return ContentItem(
        video_id=vid, title=f"视频{vid}", url=f"https://www.bilibili.com/video/{vid}",
        published_at=datetime(2026, 6, 25, tzinfo=UTC), category=cat,
        sampled_at=datetime(2026, 8, 16, tzinfo=UTC),
        search_term_used="测试", search_rank=1, sampling_reason="测试夹具",
    )


def make_post(pid, vid, text, day, likes=0, parent=None):
    return CommunityPost(
        post_id=pid, video_id=vid, parent_id=parent, text=text,
        published_at=datetime(2026, 7, 1, tzinfo=UTC) + timedelta(days=day),
        likes=likes, anon_user_id=f"u{pid}", source_url=f"https://www.bilibili.com/video/{vid}",
    )


def fixture_data():
    study = make_study()
    videos = [make_video("BV1", "official"), make_video("BV2", "review")]
    posts = [
        make_post("p1", "BV1", "这版本新地图的音乐太好听了，探索感拉满", 1, likes=10),
        make_post("p2", "BV1", "深渊数值膨胀太严重了，平民玩家根本打不满", 2, likes=500),
        make_post("p3", "BV2", "抽卡又歪了，这卡池安排真离谱", 3, likes=50),
        make_post("p4", "BV2", "剧情演出不错，但结尾有点仓促", 5, likes=20),
        make_post("p5", "BV1", "闪退两次了，赶紧修", 8, likes=5),
        make_post("p6", "BV2", "卡池歪了但新角色建模真心好看", 10, likes=80),
    ]
    return study, posts, videos


def ann_json(relevant, topics, stance, emotion, intensity=1, irony="无",
             intent="体验陈述", issue=None, conf=0.9, ev=""):
    return json.dumps({
        "relevant": relevant, "topics": topics, "stance": stance, "emotion": emotion,
        "intensity": intensity, "irony": irony, "intent": intent, "issue_type": issue,
        "confidence": conf, "evidence_span": ev or "原文摘录",
        "abstain_reason": None if relevant is not None else "语境不足",
    }, ensure_ascii=False)


SCRIPT = {
    "p1": ann_json(True, ["地图与探索"], "支持", "喜悦", 2, ev="音乐太好听"),
    "p2": ann_json(True, ["平衡与强度", "战斗与玩法"], "反对", "愤怒", 3,
                   intent="问题报告", issue="数值争议", conf=0.55, ev="数值膨胀"),
    "p3": ann_json(True, ["抽卡与商业化"], "反对", "失望", 2, ev="又歪了"),
    "p4": ann_json(True, ["剧情与世界观"], "混合", "失望", 1, ev="结尾仓促"),
    "p5": ann_json(True, ["性能与缺陷"], "反对", "愤怒", 2,
                   intent="问题报告", issue="技术故障", ev="闪退"),
    "p6": ann_json(True, ["抽卡与商业化", "角色设计与美术"], "混合", "喜悦", 1, ev="建模好看"),
}


@pytest.fixture
def scripted_env():
    register_scripted("annotate-v1", SCRIPT)
    return ScriptedLLM()


class TestPipelineEndToEnd:
    def test_full_run_produces_all_artifacts(self, tmp_path, scripted_env):
        study, posts, videos = fixture_data()
        deps = HarnessDeps(scripted_env)
        result = run_pipeline(study, posts, videos, deps, runs_dir=tmp_path)
        run_dir = tmp_path / result.run.run_id
        # manifest/state/各阶段产物/报告
        assert (run_dir / "manifest.json").exists()
        assert (run_dir / "state.json").exists()
        for stage in STAGES:
            assert (run_dir / f"{stage}.json").exists(), f"缺少 {stage}.json"
            assert result.run.stage_states[stage].status == StageStatus.DONE
        assert result.run.status == RunStatus.COMPLETED
        # 标注正确落位
        anns = result.state["annotations"]
        assert len(anns) == 6
        by_id = {a["post_id"]: a for a in anns}
        assert by_id["p1"]["stance"] == "支持"
        # 指标由 Python 计算
        m = result.state["metrics"]
        assert m["dataset"]["relevant_posts"] == 6
        assert "地图与探索" in m["topics"]
        assert m["scope_statement"].startswith("所采样的")
        # 结论验证通过 + 报告产出
        assert result.state["verify_result"]["passed"]
        html = result.state["report_html"]
        assert "版本社区复盘报告" in html
        assert "所采样的 B 站讨论" in html
        assert (run_dir / "report.html").exists()

    def test_report_contains_evidence_links(self, tmp_path, scripted_env):
        study, posts, videos = fixture_data()
        result = run_pipeline(study, posts, videos, HarnessDeps(scripted_env), runs_dir=tmp_path)
        html = result.state["report_html"]
        assert 'href="https://www.bilibili.com/video/' in html


class TestCheckpointResume:
    def test_kill_then_resume_no_recompute(self, tmp_path, scripted_env):
        study, posts, videos = fixture_data()
        run_id = "resume-test-001"
        with pytest.raises(RuntimeError, match="injected failure"):
            run_pipeline(study, posts, videos, HarnessDeps(scripted_env),
                         runs_dir=tmp_path, run_id=run_id, fail_at_stage="annotate_cheap")
        store = CheckpointStore(tmp_path / run_id)
        run = store.load_manifest()
        assert run.stage_states["normalize"].status == StageStatus.DONE
        assert run.stage_states["annotate_cheap"].status == StageStatus.FAILED
        # 续跑
        scripted2 = ScriptedLLM()
        result = run_pipeline(study, posts, videos, HarnessDeps(scripted2),
                              runs_dir=tmp_path, run_id=run_id)
        assert result.run.status == RunStatus.COMPLETED
        # 前两阶段被跳过、未重复执行（cheap 只跑一次×6条）
        assert scripted2.usage.calls == 6 + len(result.state["review_queue"])

    def test_dataset_hash_mismatch_refuses_resume(self, tmp_path, scripted_env):
        study, posts, videos = fixture_data()
        run_id = "hash-mismatch"
        run_pipeline(study, posts, videos, HarnessDeps(scripted_env), runs_dir=tmp_path, run_id=run_id)
        posts2 = posts[:-1]
        with pytest.raises(ValueError, match="哈希"):
            run_pipeline(study, posts2, videos, HarnessDeps(ScriptedLLM()),
                         runs_dir=tmp_path, run_id=run_id)


class TestLock:
    def test_second_lock_rejected(self, tmp_path):
        with RunLock(tmp_path / ".lock"):
            with pytest.raises(RunLockError):
                with RunLock(tmp_path / ".lock"):
                    pass

    def test_lock_released_after_exit(self, tmp_path):
        with RunLock(tmp_path / ".lock"):
            pass
        with RunLock(tmp_path / ".lock"):
            pass


class TestRouteReview:
    def _ann(self, pid, conf=0.9, irony="无", topics=None):
        return Annotation(post_id=pid, relevant=True, topics=topics or [],
                          confidence=conf, irony=irony, stage=AnnotateStage.CHEAP)

    def test_low_confidence_routed(self):
        anns = {"a": self._ann("a", conf=0.4), "b": self._ann("b", conf=0.95)}
        q = route_review(["a", "b"], anns, {"a": 1, "b": 1}, set(), {})
        assert q == ["a"]

    def test_irony_routed(self):
        anns = {"a": self._ann("a", irony="无法判断"), "b": self._ann("b")}
        q = route_review(["a", "b"], anns, {"a": 1, "b": 1}, set(), {})
        assert q == ["a"]

    def test_high_likes_routed(self):
        anns = {p: self._ann(p) for p in ["a", "b", "c"]}
        likes = {"a": 1, "b": 2, "c": 10000}
        q = route_review(["a", "b", "c"], anns, likes, set(), {})
        assert "c" in q and "a" not in q

    def test_missing_annotation_routed(self):
        q = route_review(["ghost"], {}, {"ghost": 1}, set(), {})
        assert q == ["ghost"]


class TestVerify:
    def test_missing_citations_rejected(self):
        r = verify_claims([Claim(claim_id="c1", text="在所采样的讨论中，X 主题占比高")])
        assert not r.passed

    def test_overreach_rejected(self):
        r = verify_claims([Claim(
            claim_id="c1", text="所有玩家都认为抽卡太贵",
            metric_ids=["m1"], evidence_ids=["e1"])])
        assert not r.passed
        assert any(v["rule"] == "过度泛化" for v in r.violations)

    def test_causal_rejected(self):
        r = verify_claims([Claim(
            claim_id="c1", text="数值膨胀导致玩家流失",
            metric_ids=["m1"], evidence_ids=["e1"])])
        assert any(v["rule"] == "因果表述" for v in r.violations)

    def test_small_sample_needs_mark(self):
        r = verify_claims([Claim(
            claim_id="c1", text="在所采样的 B 站讨论中，X 讨论上升", topic_sample_size=12,
            metric_ids=["m1"], evidence_ids=["e1"])])
        assert any(v["rule"] == "小样本" for v in r.violations)

    def test_valid_claim_passes(self):
        r = verify_claims([Claim(
            claim_id="c1", text="在所采样的 B 站讨论中，X 讨论占比 12%（样本 320 条）",
            topic_sample_size=320, metric_ids=["m1"], evidence_ids=["e1", "e2"])])
        assert r.passed


class TestLangGraphStructure:
    def test_graph_compiles(self):
        g = build_langgraph(HarnessDeps(ScriptedLLM()))
        app = g.compile()
        assert app is not None

    def test_stages_match_graph_nodes(self):
        from liveops.harness.nodes import STAGES as S
        assert S[:3] == ["normalize", "relevance_filter", "embed_cluster"]
        assert "verify" in S
