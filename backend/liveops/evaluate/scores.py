"""评测核心：Macro-F1、多标签 F1、混淆矩阵、Cohen's Kappa、ECE、弃权率。

纯 Python 精确实现（手工可验证），数值与其他库对照过再交给前端。
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Sequence


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f1


def macro_f1(y_true: Sequence[str | None], y_pred: Sequence[str | None],
             labels: Sequence[str]) -> dict[str, Any]:
    """宏平均 F1。None（弃权）不计入预测正确性，单独报告弃权率。"""
    assert len(y_true) == len(y_pred)
    abstain = sum(1 for p in y_pred if p is None)
    per: dict[str, dict[str, float]] = {}
    f1s = []
    for lab in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p == lab)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != lab and p == lab)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p != lab)
        p, r, f1 = prf(tp, fp, fn)
        per[lab] = {"precision": p, "recall": r, "f1": f1}
        f1s.append(f1)
    return {
        "macro_f1": sum(f1s) / len(f1s) if f1s else 0.0,
        "per_label": per,
        "n": len(y_true),
        "abstain": abstain,
        "abstain_rate": abstain / len(y_pred) if y_pred else 0.0,
    }


def multilabel_macro_f1(y_true: Sequence[set[str]], y_pred: Sequence[set[str]],
                        labels: Sequence[str]) -> dict[str, Any]:
    """多标签（主题）宏 F1：每标签二值化。"""
    per: dict[str, dict[str, float]] = {}
    f1s = []
    for lab in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if lab in t and lab in p)
        fp = sum(1 for t, p in zip(y_true, y_pred) if lab not in t and lab in p)
        fn = sum(1 for t, p in zip(y_true, y_pred) if lab in t and lab not in p)
        p, r, f1 = prf(tp, fp, fn)
        per[lab] = {"precision": p, "recall": r, "f1": f1}
        f1s.append(f1)
    return {"macro_f1": sum(f1s) / len(f1s) if f1s else 0.0, "per_label": per, "n": len(y_true)}


def confusion_matrix(y_true: Sequence[str], y_pred: Sequence[str],
                     labels: Sequence[str]) -> dict[str, Any]:
    idx = {l: i for i, l in enumerate(labels)}
    m = [[0] * len(labels) for _ in labels]
    for t, p in zip(y_true, y_pred):
        if t in idx and p in idx:
            m[idx[t]][idx[p]] += 1
    return {"labels": list(labels), "matrix": m}


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float | None:
    """两人标注一致性。"""
    assert len(a) == len(b)
    n = len(a)
    if n == 0:
        return None
    labels = sorted(set(a) | set(b))
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum((ca[l] / n) * (cb[l] / n) for l in labels)
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def expected_calibration_error(confidences: Sequence[float],
                               corrects: Sequence[bool], bins: int = 10) -> float:
    """ECE = Σ (bin_n / N) * |bin_acc - bin_conf|。"""
    n = len(confidences)
    if n == 0:
        return 0.0
    ece = 0.0
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        idxs = [j for j, c in enumerate(confidences) if lo <= c < hi or (i == bins - 1 and c == 1.0)]
        if not idxs:
            continue
        acc = sum(1 for j in idxs if corrects[j]) / len(idxs)
        conf = sum(confidences[j] for j in idxs) / len(idxs)
        ece += len(idxs) / n * abs(acc - conf)
    return ece


def grouped_split(video_ids: Sequence[str], test_size: float = 0.3,
                  seed: int = 42) -> dict[str, list[int]]:
    """按视频分组切分：同一视频的评论不跨训练/测试。返回 index 集合。"""
    import random
    groups: dict[str, list[int]] = {}
    for i, v in enumerate(video_ids):
        groups.setdefault(v, []).append(i)
    keys = sorted(groups.keys())
    rng = random.Random(seed)
    rng.shuffle(keys)
    n_test_groups = max(1, round(len(keys) * test_size)) if len(keys) > 1 else 1
    test_groups = set(keys[:n_test_groups])
    train_idx = [i for k in keys[n_test_groups:] for i in groups[k]]
    test_idx = [i for k in keys if k in test_groups for i in groups[k]]
    return {"train": sorted(train_idx), "test": sorted(test_idx),
            "train_videos": [k for k in keys if k not in test_groups],
            "test_videos": sorted(test_groups)}


@dataclass
class EvalReport:
    relevance: dict[str, Any] | None = None
    topics: dict[str, Any] | None = None
    stance: dict[str, Any] | None = None
    emotion: dict[str, Any] | None = None
    irony: dict[str, Any] | None = None
    confusion: dict[str, dict[str, Any]] = field(default_factory=dict)
    kappa: float | None = None
    ece: float | None = None
    abstain_rate: float = 0.0
    n_gold: int = 0
    n_evaluated: int = 0
    cost_cny: float | None = None
    throughput_per_min: float | None = None
    notes: list[str] = field(default_factory=list)
