"""嵌入与聚类测试：降级链、质心分配、新兴主题、KMeans。"""

import pytest

from liveops.cluster import (
    assign_topics,
    compute_topic_centroids,
    cosine,
    simple_kmeans,
    TOPIC_DESCRIPTIONS,
)
from liveops.embed import _hash_embed_one, embed_texts
from liveops.schema import FIXED_TOPICS


class TestEmbed:
    def test_hash_embed_deterministic(self):
        a = _hash_embed_one("深渊太难了")
        b = _hash_embed_one("深渊太难了")
        assert a == b

    def test_hash_embed_normalized(self):
        v = _hash_embed_one("任意文本内容")
        assert abs(sum(x * x for x in v) - 1.0) < 1e-6

    def test_similar_texts_closer_than_different(self):
        v1 = _hash_embed_one("这版本抽卡池太歪了保底又歪")
        v2 = _hash_embed_one("这版本卡池太歪了保底歪了")
        v3 = _hash_embed_one("剧情演出做得真好哭了")
        assert cosine(v1, v2) > cosine(v1, v3)

    def test_embed_texts_falls_back_without_heavy_deps(self, monkeypatch):
        import liveops.embed as em
        # sentence-transformers 未安装或加载失败 → 哈希降级，不抛异常
        res = embed_texts(["文本一", "文本二"])
        assert res.embed_quality in ("bge-m3", "bge-small", "hash-degraded")
        assert len(res.vectors) == 2

    def test_degraded_quality_reported(self, monkeypatch):
        import builtins
        import liveops.embed as em
        real_import = builtins.__import__

        def no_st(name, *a, **k):
            if name.startswith("sentence_transformers"):
                raise ImportError("blocked in test")
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", no_st)
        res = em.embed_texts(["文本"])
        assert res.embed_quality == "hash-degraded"


class TestCluster:
    def test_topic_descriptions_cover_all(self):
        assert set(TOPIC_DESCRIPTIONS.keys()) == set(FIXED_TOPICS)

    def test_centroids_and_assignment(self):
        texts = ["抽卡保底又歪了卡池太坑", "新地图探索解谜真好玩", "完全无关的话"]
        cents = compute_topic_centroids(lambda ts: [_hash_embed_one(t) for t in ts])
        assert set(cents.keys()) == set(FIXED_TOPICS)
        vecs = [_hash_embed_one(t) for t in texts]
        res = assign_topics(["p1", "p2", "p3"], texts, vecs, cents,
                            threshold=0.05, min_cluster_size=2)
        assert len(res.assignments) == 3
        # 阈值极低时前两条应命中主题
        assert res.assignments["p1"].topics or res.assignments["p1"].new_topic

    def test_new_topic_candidates_min_size(self):
        texts = [f"独特话题内容变体{i}号讨论" for i in range(6)] + ["正常主题文本"]
        vecs = [_hash_embed_one(t) for t in texts]
        cents = compute_topic_centroids(lambda ts: [_hash_embed_one(t) for t in ts])
        res = assign_topics([f"p{i}" for i in range(7)], texts, vecs, cents,
                            threshold=0.99, min_cluster_size=2)
        # 阈值极高 → 全部未命中固定主题 → 聚类产生候选
        assert len(res.new_topic_candidates) >= 1
        cand = res.new_topic_candidates[0]
        assert cand["size"] >= 2 and cand["new_topic_id"].startswith("new:")

    def test_high_threshold_no_hits_no_candidates(self):
        texts = ["甲", "乙"]
        vecs = [_hash_embed_one(t) for t in texts]
        cents = compute_topic_centroids(lambda ts: [_hash_embed_one(t) for t in ts])
        res = assign_topics(["p1", "p2"], texts, vecs, cents,
                            threshold=0.99, min_cluster_size=5)
        assert res.new_topic_candidates == []
        assert all(not a.topics for a in res.assignments.values())

    def test_kmeans_clusters_similar(self):
        group_a = [_hash_embed_one(f"抽卡歪了保底太坑{i}") for i in range(5)]
        group_b = [_hash_embed_one(f"剧情文案真好哭{i}") for i in range(5)]
        labels, cents = simple_kmeans(group_a + group_b, k=2)
        assert len(set(labels[:5])) == 1 and len(set(labels[5:])) == 1
        assert labels[0] != labels[5]

    def test_kmeans_empty(self):
        labels, cents = simple_kmeans([], k=3)
        assert labels == []
