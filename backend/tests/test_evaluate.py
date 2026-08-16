"""评测框架测试：手工小样本对照精确值。"""

import math

import pytest

from liveops.evaluate import (
    cohen_kappa,
    confusion_matrix,
    expected_calibration_error,
    grouped_split,
    macro_f1,
    multilabel_macro_f1,
)
from liveops.evaluate.gold import GoldLabel, gold_by_post, double_annotated
from datetime import datetime, timezone


class TestMacroF1:
    def test_perfect(self):
        r = macro_f1(["支持", "反对"], ["支持", "反对"], ["支持", "反对"])
        assert r["macro_f1"] == 1.0 and r["abstain"] == 0

    def test_hand_computed(self):
        # 支持类: tp=1 fp=1 fn=1 → p=0.5 r=0.5 f1=0.5
        # 反对类: tp=1 fp=1 fn=1 → f1=0.5
        y_true = ["支持", "支持", "反对", "反对"]
        y_pred = ["支持", "反对", "支持", "反对"]
        r = macro_f1(y_true, y_pred, ["支持", "反对"])
        assert r["per_label"]["支持"]["f1"] == pytest.approx(0.5)
        assert r["macro_f1"] == pytest.approx(0.5)

    def test_abstain_counted_separately(self):
        y_true = ["支持", "反对", "中立"]
        y_pred = ["支持", None, "中立"]
        r = macro_f1(y_true, y_pred, ["支持", "反对", "中立"])
        assert r["abstain"] == 1
        assert r["abstain_rate"] == pytest.approx(1 / 3)
        # 弃权样本：真值类 fn+1，预测无命中 → 反对 f1=0
        assert r["per_label"]["反对"]["f1"] == 0.0
        assert r["per_label"]["支持"]["f1"] == 1.0

    def test_empty_labels(self):
        r = macro_f1([], [], [])
        assert r["macro_f1"] == 0.0


class TestMultilabel:
    def test_hand_computed(self):
        y_true = [{"A", "B"}, {"A"}]
        y_pred = [{"A"}, {"A", "C"}]
        r = multilabel_macro_f1(y_true, y_pred, ["A", "B", "C"])
        assert r["per_label"]["A"]["f1"] == pytest.approx(1.0)  # tp=2 fp=0 fn=0
        assert r["per_label"]["B"]["f1"] == 0.0
        assert r["per_label"]["C"]["f1"] == 0.0


class TestConfusion:
    def test_matrix(self):
        m = confusion_matrix(["支持", "反对"], ["支持", "支持"], ["支持", "反对"])
        assert m["matrix"] == [[1, 0], [1, 0]]

    def test_ignores_unknown(self):
        m = confusion_matrix(["支持", "X"], ["支持", "支持"], ["支持", "反对"])
        assert m["matrix"] == [[1, 0], [0, 0]]


class TestKappa:
    def test_perfect_agreement(self):
        assert cohen_kappa(["a", "b", "a"], ["a", "b", "a"]) == pytest.approx(1.0)

    def test_chance_agreement(self):
        # po=0.5, pe=0.5 → kappa=0
        k = cohen_kappa(["a", "b"], ["a", "a"])
        po = 0.5
        pe = 0.5 * 1.0 + 0.5 * 0.0
        assert k == pytest.approx((po - pe) / (1 - pe))

    def test_hand_example(self):
        # 经典例子: po=0.6, pe=0.5 → kappa=0.2
        a = ["yes"] * 6 + ["no"] * 4
        b = ["yes"] * 5 + ["no"] * 0 + ["yes"] * 0 + ["no"] * 4  # 5+0, 1yes+4no
        b = ["yes", "yes", "yes", "yes", "yes", "no", "no", "no", "no", "yes"]
        k = cohen_kappa(a, b)
        po = sum(1 for x, y in zip(a, b) if x == y) / 10  # 4+4=8? 手算
        # a: yes×6 no×4; b: yes×6 no×4; 同意= yes-yes 5 + no-no 3 = 8
        assert po == pytest.approx(0.8)
        pe = 0.6 * 0.6 + 0.4 * 0.4  # 0.52
        assert k == pytest.approx((0.8 - 0.52) / 0.48)


class TestECE:
    def test_perfect_calibration_conf_1(self):
        ece = expected_calibration_error([1.0, 1.0, 1.0], [True, True, True])
        assert ece == pytest.approx(0.0)

    def test_overconfident(self):
        # 全部自信 1.0 但只对一半 → ECE=0.5
        ece = expected_calibration_error([1.0] * 4, [True, True, False, False])
        assert ece == pytest.approx(0.5)

    def test_binned(self):
        # conf 0.5 处一半正确 → 该桶 |0.5-0.5|=0
        ece = expected_calibration_error([0.5, 0.5], [True, False])
        assert ece == pytest.approx(0.0)


class TestGroupedSplit:
    def test_no_video_leak(self):
        vids = ["v1"] * 5 + ["v2"] * 5 + ["v3"] * 5 + ["v4"] * 5
        s = grouped_split(vids, test_size=0.5, seed=1)
        train_v = {vids[i] for i in s["train"]}
        test_v = {vids[i] for i in s["test"]}
        assert not (train_v & test_v)
        assert set(s["train_videos"]) == train_v
        assert set(s["test_videos"]) == test_v
        assert len(s["train"]) + len(s["test"]) == len(vids)

    def test_deterministic(self):
        vids = [f"v{i % 7}" for i in range(30)]
        a = grouped_split(vids, seed=9)
        b = grouped_split(vids, seed=9)
        assert a == b


def _gold(pid, annotator, atype, stance):
    return GoldLabel(post_id=pid, study_id="s", annotator=annotator,
                     annotator_type=atype, annotated_at=datetime.now(timezone.utc),
                     relevant=True, topics=["战斗与玩法"], stance=stance)


class TestGoldLayers:
    def test_human_overrides_seed(self):
        labels = [_gold("p1", "dev-agent", "strong_model_seed", "支持"),
                  _gold("p1", "user-a", "human", "反对"),
                  _gold("p2", "dev-agent", "strong_model_seed", "中立")]
        by = gold_by_post(labels)
        assert by["p1"].stance == "反对" and by["p1"].annotator_type == "human"
        assert by["p2"].annotator_type == "strong_model_seed"

    def test_double_annotated(self):
        labels = [
            _gold("p1", "a", "human", "支持"), _gold("p2", "a", "human", "反对"),
            _gold("p1", "b", "human", "支持"), _gold("p3", "b", "human", "中立"),
        ]
        d = double_annotated(labels)
        assert d["annotators"] == ["a", "b"]
        assert set(d["common_post_ids"]) == {"p1"}

    def test_no_double(self):
        labels = [_gold("p1", "a", "human", "支持")]
        assert double_annotated(labels) == {}
