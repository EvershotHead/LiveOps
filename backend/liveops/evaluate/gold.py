"""金标准加载与两层口径管理（strong_model_seed / human）。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..schema import FIXED_TOPICS, AnnotatorType, GoldLabel


def load_gold(path: str | Path) -> list[GoldLabel]:
    p = Path(path)
    labels: list[GoldLabel] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            labels.append(GoldLabel.model_validate(json.loads(line)))
    return labels


def save_gold(labels: list[GoldLabel], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for g in labels:
            f.write(g.model_dump_json() + "\n")


def split_by_annotator_type(labels: list[GoldLabel]) -> dict[str, list[GoldLabel]]:
    out: dict[str, list[GoldLabel]] = {"strong_model_seed": [], "human": []}
    for g in labels:
        out[g.annotator_type.value].append(g)
    return out


def gold_by_post(labels: list[GoldLabel]) -> dict[str, GoldLabel]:
    """同 post 多层时 human 层优先（人工复核覆盖种子）。"""
    by: dict[str, GoldLabel] = {}
    for g in labels:
        if g.post_id not in by or g.annotator_type == AnnotatorType.HUMAN:
            by[g.post_id] = g
    return by


def double_annotated(labels: list[GoldLabel]) -> dict[str, list[GoldLabel]]:
    """post_id -> 多标注员标签（≥2 人时用于 Kappa）。按 annotator 标识分组。"""
    by_annotator: dict[str, dict[str, GoldLabel]] = {}
    for g in labels:
        by_annotator.setdefault(g.annotator, {})[g.post_id] = g
    annotators = sorted(by_annotator)
    if len(annotators) < 2:
        return {}
    a, b = by_annotator[annotators[0]], by_annotator[annotators[1]]
    common = sorted(set(a.keys()) & set(b.keys()))
    return {"annotators": annotators, "common_post_ids": common,
            "a": {pid: a[pid] for pid in common}, "b": {pid: b[pid] for pid in common}}


ALL_TOPIC_LABELS = list(FIXED_TOPICS)
STANCES = ["支持", "反对", "中立", "混合", "不明确"]
EMOTIONS = ["喜悦", "期待", "惊讶", "失望", "愤怒", "焦虑", "调侃玩梗", "无明显情绪"]
IRONY = ["无", "可能", "明显", "无法判断"]
