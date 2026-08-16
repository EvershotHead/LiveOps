"""Canonical Schema 测试：六对象 roundtrip、最少字段、窗口、枚举一致性。"""

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from liveops.schema import (
    FIXED_TOPICS,
    LABEL_SET_VERSION,
    Annotation,
    AnalysisRun,
    CommunityPost,
    ContentItem,
    GoldLabel,
    HumanReview,
    PhaseWindow,
    StudyConfig,
    AnnotatorType,
    Emotion,
    Irony,
    Stance,
    is_valid_topic,
)

UTC = timezone.utc


def make_study() -> StudyConfig:
    return StudyConfig(
        study_id="genshin-6.8",
        game="genshin",
        version_label="6.8",
        t0_date=date(2026, 7, 1),
        search_terms=["原神6.8", "原神 空月之谐谑"],
    )


def make_video() -> ContentItem:
    return ContentItem(
        video_id="BV1xx411c7mD",
        title="【原神】6.8版本PV",
        url="https://www.bilibili.com/video/BV1xx411c7mD",
        published_at=datetime(2026, 6, 25, 12, 0, tzinfo=UTC),
        category="official",
        author_type="official",
        sampled_at=datetime(2026, 8, 16, tzinfo=UTC),
        search_term_used="原神6.8",
        search_rank=1,
        sampling_reason="官方版本PV，官方物料类种子",
    )


def make_post() -> CommunityPost:
    return CommunityPost(
        post_id="rpid-0001",
        video_id="BV1xx411c7mD",
        text="这版本地图音乐太神了",
        published_at=datetime(2026, 7, 2, 10, 0, tzinfo=UTC),
        likes=233,
        reply_count=2,
        anon_user_id="a1b2c3d4e5f60718",
        collected_at=datetime(2026, 8, 16, tzinfo=UTC),
        source_url="https://www.bilibili.com/video/BV1xx411c7mD",
    )


class TestStudyConfig:
    def test_roundtrip(self):
        s = make_study()
        d = s.model_dump(mode="json")
        assert StudyConfig.model_validate(d) == s

    def test_default_window_t7_t28(self):
        w = PhaseWindow()
        assert w.preheat == (-7, -1)
        assert w.launch == (0, 7)
        assert w.ferment == (8, 28)
        assert w.in_window(-7) and w.in_window(28)
        assert not w.in_window(-8)
        assert not w.in_window(29)
        assert w.phase_of(-3) == "preheat"
        assert w.phase_of(5) == "launch"
        assert w.phase_of(20) == "ferment"
        assert w.phase_of(40) is None

    def test_extra_field_forbidden(self):
        d = make_study().model_dump(mode="json")
        d["hacked"] = 1
        with pytest.raises(ValidationError):
            StudyConfig.model_validate(d)


class TestContentItemAndPost:
    def test_roundtrip(self):
        v = make_video()
        assert ContentItem.model_validate(v.model_dump(mode="json")) == v
        p = make_post()
        assert CommunityPost.model_validate(p.model_dump(mode="json")) == p

    def test_empty_video_id_rejected(self):
        d = make_video().model_dump(mode="json")
        d["video_id"] = "  "
        with pytest.raises(ValidationError):
            ContentItem.model_validate(d)

    def test_empty_text_rejected(self):
        d = make_post().model_dump(mode="json")
        d["text"] = "   "
        with pytest.raises(ValidationError):
            CommunityPost.model_validate(d)


class TestAnnotation:
    def test_roundtrip(self):
        a = Annotation(
            post_id="rpid-0001",
            relevant=True,
            topics=["地图与探索", "角色设计与美术"],
            stance=Stance.SUPPORT,
            emotion=Emotion.JOY,
            intensity=2,
            irony=Irony.NONE,
            confidence=0.9,
            evidence_span="地图音乐太神了",
            model="mock-cheap",
            prompt_version="v1",
        )
        assert Annotation.model_validate(a.model_dump(mode="json")) == a

    def test_new_topic_placeholder_allowed(self):
        a = Annotation(post_id="p1", relevant=True, topics=["new:c3"], abstain_reason=None)
        assert "new:c3" in a.topics

    def test_invalid_topic_rejected(self):
        with pytest.raises(ValidationError):
            Annotation(post_id="p1", relevant=True, topics=["不存在的主题"])

    def test_abstain_requires_reason(self):
        with pytest.raises(ValidationError):
            Annotation(post_id="p1", relevant=None, abstain_reason="")

    def test_intensity_bounds(self):
        with pytest.raises(ValidationError):
            Annotation(post_id="p1", relevant=True, intensity=4)

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            Annotation(post_id="p1", relevant=True, confidence=1.5)


class TestGoldAndReview:
    def test_gold_seed_annotator_type(self):
        g = GoldLabel(
            post_id="p1",
            study_id="s1",
            annotator="dev-agent",
            annotator_type=AnnotatorType.STRONG_MODEL_SEED,
            annotated_at=datetime(2026, 8, 16, tzinfo=UTC),
            relevant=True,
            topics=["战斗与玩法"],
            stance=Stance.OPPOSE,
        )
        assert g.annotator_type == "strong_model_seed"
        assert GoldLabel.model_validate(g.model_dump(mode="json")) == g

    def test_human_review_roundtrip(self):
        r = HumanReview(
            review_id="rv1",
            post_id="p1",
            field="stance",
            before="不明确",
            after="反对",
            reason="结合楼中楼语境，明显在批评卡池安排",
            reviewer="user-a",
            reviewed_at=datetime(2026, 8, 16, tzinfo=UTC),
        )
        assert HumanReview.model_validate(r.model_dump(mode="json")) == r


class TestAnalysisRun:
    def test_roundtrip_with_stages(self):
        run = AnalysisRun(
            run_id="run-001",
            study_id="genshin-6.8",
            created_at=datetime(2026, 8, 16, tzinfo=UTC),
            dataset_hash="abc123",
            config_snapshot=make_study().model_dump(mode="json"),
            models={"cheap": "glm-4-flash", "strong": "glm-4.7"},
            prompt_versions={"annotate": "v1"},
            code_version="git-sha-000",
            stage_states={"normalize": {"stage": "normalize", "status": "done", "output_hash": "h1"}},
        )
        assert AnalysisRun.model_validate(run.model_dump(mode="json")) == run


class TestLabelSet:
    def test_12_fixed_topics(self):
        assert len(FIXED_TOPICS) == 12
        assert "抽卡与商业化" in FIXED_TOPICS

    def test_topic_validity(self):
        assert is_valid_topic("性能与缺陷")
        assert is_valid_topic("new:cluster9")
        assert not is_valid_topic("new:")
        assert not is_valid_topic("随便")

    def test_label_version_recorded(self):
        assert LABEL_SET_VERSION == "v1.0"
