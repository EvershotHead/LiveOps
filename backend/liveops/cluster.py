"""主题分配与新兴主题发现。

方法：
1. 12 个固定主题的描述文本 + 关键词示例 → 嵌入质心。
2. 评论嵌入与质心余弦相似度，超过阈值的主题命中（可多命中）。
3. 未命中任何固定主题的相关评论 → KMeans 聚类，簇大小 ≥ min_cluster_size
   的簇成为"新兴主题候选"（new:c{i}），由人工命名后转正。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .schema import FIXED_TOPICS

TOPIC_DESCRIPTIONS: dict[str, str] = {
    "角色设计与美术": "角色立绘 建模 服装 动作 配音 美术风格 好看 丑 出新角色",
    "战斗与玩法": "战斗机制 操作 手感 玩法 战斗系统 新机制 连招 闪避 格挡",
    "剧情与世界观": "剧情 主线 支线 文案 世界观 设定 剧情演出 结局 角色故事",
    "地图与探索": "新地图 探索 解谜 宝箱 地图设计 场景 音乐 风景 跑图",
    "版本内容量": "版本内容 内容量 长草 更新频率 没内容 内容太少 一天肝完",
    "活动设计": "活动 限时活动 活动玩法 活动奖励 活动门槛 打活动 活动太难太简单",
    "养成与资源": "圣遗物 声骸 养成 体力 素材 资源 树脂 刷本 毕业词条",
    "抽卡与商业化": "抽卡 卡池 保底 歪 定价 礼包 月卡 付费 皮肤价格 售价",
    "平衡与强度": "强度 数值 平衡 深渊 满星 角色强弱 数值膨胀 泛用性 T0",
    "性能与缺陷": "卡顿 掉帧 闪退 bug 优化 发热 网络 延迟 修复 补丁",
    "界面与便利性": "界面 UI 菜单 操作不便 跳过 一键 便利性 快捷 图标 小地图",
    "官方沟通与社区生态": "官方 公告 回应 补偿 社区 节奏 舆论 UP主 玩家吵架 官方装死",
}


@dataclass
class TopicAssignment:
    post_id: str
    topics: list[str] = field(default_factory=list)
    new_topic: str | None = None


@dataclass
class ClusterResult:
    assignments: dict[str, TopicAssignment]
    topic_centroids: dict[str, list[float]]
    new_topic_candidates: list[dict] = field(default_factory=list)
    embed_quality: str = ""


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def compute_topic_centroids(embed_fn) -> dict[str, list[float]]:
    """embed_fn(texts) -> list[vector]。固定主题 → 质心。"""
    texts = [f"{t} {TOPIC_DESCRIPTIONS[t]}" for t in FIXED_TOPICS]
    vecs = embed_fn(texts)
    return {t: v for t, v in zip(FIXED_TOPICS, vecs)}


def simple_kmeans(vectors: list[list[float]], k: int, *, seed: int = 42, iters: int = 25):
    """轻量 KMeans（cosine 距离），避免引入 sklearn 重依赖。"""
    if not vectors:
        return [], []
    k = min(k, len(vectors))
    n = len(vectors[0])
    # 确定性初始化：均匀抽样
    step = max(1, len(vectors) // k)
    centroids = [vectors[i][:] for i in range(0, len(vectors), step)][:k]
    labels = [0] * len(vectors)
    for _ in range(iters):
        changed = False
        for i, v in enumerate(vectors):
            best, best_s = 0, -2.0
            for ci, c in enumerate(centroids):
                s = cosine(v, c)
                if s > best_s:
                    best, best_s = ci, s
            if labels[i] != best:
                labels[i] = best
                changed = True
        if not changed:
            break
        # 更新质心
        sums = [[0.0] * n for _ in range(k)]
        counts = [0] * k
        for i, v in enumerate(vectors):
            ci = labels[i]
            counts[ci] += 1
            for j in range(n):
                sums[ci][j] += v[j]
        for ci in range(k):
            if counts[ci]:
                norm = math.sqrt(sum(x * x for x in sums[ci])) or 1.0
                centroids[ci] = [x / norm for x in sums[ci]]
    return labels, centroids


def assign_topics(
    post_ids: list[str],
    texts: list[str],
    vectors: list[list[float]],
    centroids: dict[str, list[float]],
    *,
    threshold: float = 0.55,
    min_cluster_size: int = 5,
) -> ClusterResult:
    """为每条评论分配固定主题；未命中者聚类发现新兴主题候选。"""
    result = ClusterResult(assignments={}, topic_centroids=centroids)
    unassigned_idx: list[int] = []

    for idx, (pid, vec) in enumerate(zip(post_ids, vectors)):
        sims = sorted(
            ((cosine(vec, c), t) for t, c in centroids.items()), reverse=True
        )
        hit = [t for s, t in sims if s >= threshold]
        result.assignments[pid] = TopicAssignment(post_id=pid, topics=hit[:4])
        if not hit:
            unassigned_idx.append(idx)

    # 新兴主题：对未命中样本聚类
    if unassigned_idx:
        vecs = [vectors[i] for i in unassigned_idx]
        k = max(2, min(8, len(unassigned_idx) // max(min_cluster_size, 1) or 2))
        labels, _ = simple_kmeans(vecs, k)
        cluster_members: dict[int, list[int]] = {}
        for i, lab in zip(unassigned_idx, labels):
            cluster_members.setdefault(lab, []).append(i)
        cid = 0
        for lab, members in sorted(cluster_members.items()):
            if len(members) >= min_cluster_size:
                new_id = f"new:c{cid}"
                cid += 1
                for mi in members:
                    pid = post_ids[mi]
                    result.assignments[pid].new_topic = new_id
                result.new_topic_candidates.append({
                    "new_topic_id": new_id,
                    "size": len(members),
                    "sample_texts": [texts[mi][:50] for mi in members[:5]],
                })
    return result
