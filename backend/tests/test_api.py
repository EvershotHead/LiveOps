"""API 测试：导入预览/校验、审核队列/提交/合并、对照、证据回溯。"""

import io
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from liveops.api.main import app
from liveops.harness.graph import HarnessDeps, run_pipeline
from liveops.llm import ScriptedLLM, register_scripted
from liveops.llm.prompts import v1
from liveops.fixtures import load_fixture


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def completed_run(tmp_path_factory):
    fx = load_fixture("synthetic_100")
    register_scripted(v1.ANNOTATE_VERSION, fx.seed_annotations)
    tmp = tmp_path_factory.mktemp("api-runs")
    result = run_pipeline(fx.study, fx.posts, fx.videos,
                          HarnessDeps(ScriptedLLM()), runs_dir=tmp)
    return result.run.run_id, tmp


@pytest.fixture
def patched_store(completed_run, monkeypatch):
    run_id, tmp = completed_run
    import liveops.service_review as sr
    _orig = sr.RunStore
    store = _orig(tmp)
    import liveops.api.routes_read as rr
    import liveops.api.routes_review as rv
    rr._store = store
    rr._review_svc = sr.ReviewService(store)
    rv._store = store
    rv._svc = sr.ReviewService(store)
    yield run_id
    rr._store = sr.RunStore()
    rr._review_svc = sr.ReviewService(sr.RunStore())
    rv._store = sr.RunStore()
    rv._svc = sr.ReviewService(sr.RunStore())


class TestHealth:
    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_mode(self, client):
        r = client.get("/api/mode")
        assert r.json()["mode"] in ("local", "demo")


class TestImport:
    def test_preview_suggests_mapping(self, client):
        csv_data = "评论内容,评论时间,链接,点赞\n好玩,2026-07-02,https://b/BV1,5\n"
        r = client.post("/api/import/preview",
                        files={"file": ("c.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")})
        assert r.status_code == 200
        d = r.json()
        assert d["suggested_mapping"]["text"] == "评论内容"
        assert len(d["preview_rows"]) == 1
        assert d["columns"] == ["评论内容", "评论时间", "链接", "点赞"]

    def test_preview_corrupt_rejected(self, client):
        r = client.post("/api/import/preview",
                        files={"file": ("x.xlsx", io.BytesIO(b"PK\x03\x04 junk"), "bin")})
        assert r.status_code == 422

    def test_validate_flow(self, client):
        csv_data = ("评论内容,评论时间,链接\n"
                    "好玩,2026-07-02 10:00:00,https://b/BV1\n"
                    "缺字段,2026-07-03,https://b/BV1\n")
        r = client.post("/api/import/preview",
                        files={"file": ("v.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")})
        token = r.json()["file_token"]
        mapping = r.json()["suggested_mapping"]
        study = {"study_id": "import-test", "game": "genshin", "version_label": "6.8",
                 "t0_date": "2026-07-01"}
        r2 = client.post("/api/import/validate",
                         json={"file_token": token, "mapping": mapping, "study": study})
        assert r2.status_code == 200
        assert r2.json()["post_count"] == 2

    def test_validate_missing_required(self, client):
        csv_data = "评论内容,点赞\n好玩,5\n"
        r = client.post("/api/import/preview",
                        files={"file": ("m.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")})
        token = r.json()["file_token"]
        r2 = client.post("/api/import/validate",
                         json={"file_token": token,
                               "mapping": {"text": "评论内容", "published_at": None, "source_url": None},
                               "study": {"study_id": "x", "game": "genshin",
                                         "version_label": "6.8", "t0_date": "2026-07-01"}})
        assert r2.status_code == 422
        assert "published_at" in r2.json()["detail"]


class TestReadAPI:
    def test_overview(self, client, patched_store):
        run_id = patched_store
        r = client.get(f"/api/runs/{run_id}/overview")
        assert r.status_code == 200
        d = r.json()
        assert d["scope_statement"].startswith("所采样的")
        assert d["top_risks"] and d["topic_shares"]

    def test_metrics_and_timeline(self, client, patched_store):
        run_id = patched_store
        assert client.get(f"/api/runs/{run_id}/metrics").status_code == 200
        tl = client.get(f"/api/runs/{run_id}/timeline").json()
        assert tl["window"] == [-7, 28] and tl["topics"]

    def test_controversy_with_evidence(self, client, patched_store):
        run_id = patched_store
        d = client.get(f"/api/runs/{run_id}/controversy").json()
        assert d["rows"]

    def test_sensitivity(self, client, patched_store):
        run_id = patched_store
        d = client.get(f"/api/runs/{run_id}/sensitivity").json()
        assert d["issue"]["base_ranks"]

    def test_report_html(self, client, patched_store):
        run_id = patched_store
        r = client.get(f"/api/runs/{run_id}/report")
        assert r.status_code == 200
        assert "所采样的 B 站讨论" in r.text

    def test_evidence_lookup(self, client, patched_store):
        run_id = patched_store
        m = client.get(f"/api/runs/{run_id}/metrics").json()
        eid = next(iter(m["evidence_items"]))
        r = client.get(f"/api/evidence/{run_id}/{eid}")
        assert r.status_code == 200
        assert r.json()["evidence_id"] == eid
        assert r.json()["source_url"].startswith("https://")

    def test_404s(self, client, patched_store):
        assert client.get("/api/runs/nope/overview").status_code == 404
        assert client.get("/api/evidence/nope/xxx").status_code == 404


class TestReviewFlow:
    def test_queue_and_submit(self, client, patched_store):
        run_id = patched_store
        q = client.get(f"/api/review/{run_id}/queue").json()
        assert q["count"] >= 1
        item = q["items"][0]
        # 与建议不同 → 必须给原因
        r_bad = client.post(f"/api/review/{run_id}/submit", json={
            "post_id": item["post_id"],
            "changes": [{"field": "stance", "after": "反对"}],
            "reason": ""})
        assert r_bad.status_code == 422
        # 带原因 → 成功
        r_ok = client.post(f"/api/review/{run_id}/submit", json={
            "post_id": item["post_id"],
            "changes": [{"field": "stance", "after": "反对"}],
            "reason": "复核后确认是批评语气"})
        assert r_ok.status_code == 200
        # 接受（无修改）→ 成功且记录
        r_acc = client.post(f"/api/review/{run_id}/submit", json={
            "post_id": q["items"][1]["post_id"], "changes": []})
        assert r_acc.status_code == 200

    def test_history_and_recompute(self, client, patched_store):
        run_id = patched_store
        h = client.get(f"/api/review/{run_id}/history").json()
        assert len(h["reviews"]) >= 2
        r = client.post(f"/api/review/{run_id}/recompute",
                        json={"apply_human_overrides": True})
        assert r.status_code == 200
        assert r.json()["human_modified"] >= 1

    def test_merged_annotation_stage_human(self, patched_store):
        run_id = patched_store
        import liveops.service_review as sr
        import liveops.api.routes_review as rv
        svc = rv._svc
        _, modified = svc.merged_annotations(run_id)
        assert modified
        anns = {a.post_id: a for a in svc.merged_annotations(run_id)[0]}
        human_staged = [a for a in anns.values() if a.stage.value == "human"]
        assert human_staged


class TestCompare:
    def test_compare_self(self, client, patched_store):
        run_id = patched_store
        d = client.get(f"/api/compare/{run_id}/{run_id}").json()
        assert d["same_relative_window"] is True
        assert "样本量差异" in d["sample_difference_note"]
        assert "胜负" in d["disclaimer"] or "不构成" in d["disclaimer"]

    def test_compare_404(self, client, patched_store):
        assert client.get("/api/compare/aaa/bbb").status_code == 404
