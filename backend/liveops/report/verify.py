"""报告验证节点：规则式检查，LLM 生成的结论必须全部通过。

规则（每条结论）：
1. 必须引用 ≥1 个 metric_id 和 ≥1 个 evidence_id。
2. 禁止把采样表述扩大为全量（"所有玩家/全体玩家/所有用户/全网"）。
3. 相关性不得写成因果（"导致/造成/致使/因此所以"连接非官方事实时降级）。
4. 引用主题样本量 <30 时必须带"小样本"标注。
5. 结论文本必须包含采样口径限定（"所采样的"等）或由报告统一口径承担。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

OVERREACH_PATTERNS = [
    r"所有玩家", r"全体玩家", r"所有用户", r"全网玩家", r"玩家们都", r"大家全都",
]
CAUSAL_PATTERNS = [r"导致", r"造成", r"致使", r"引发了?玩家流失", r"直接造成"]
SMALL_SAMPLE_MARK = "小样本"
SMALL_SAMPLE_N = 30
SCOPE_PATTERN = r"所采样的|采样(的|内)|样本(中|内)|B\s*站(社区)?讨论"


@dataclass
class Claim:
    claim_id: str
    text: str
    metric_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    topic_sample_size: int | None = None


@dataclass
class VerifyResult:
    passed: bool
    violations: list[dict] = field(default_factory=list)

    def why(self) -> str:
        return "; ".join(
            f"[{v['claim_id']}] {v['rule']}: {v['detail']}" for v in self.violations
        )


def verify_claims(claims: list[Claim]) -> VerifyResult:
    res = VerifyResult(passed=True)
    for c in claims:
        if not c.metric_ids:
            res.violations.append({"claim_id": c.claim_id, "rule": "引用", "detail": "缺少 metric_id 引用"})
        if not c.evidence_ids:
            res.violations.append({"claim_id": c.claim_id, "rule": "引用", "detail": "缺少 evidence_id 引用"})
        for pat in OVERREACH_PATTERNS:
            if re.search(pat, c.text):
                res.violations.append({
                    "claim_id": c.claim_id, "rule": "过度泛化",
                    "detail": f"出现『{pat}』，应表述为『所采样的 B 站讨论』",
                })
        for pat in CAUSAL_PATTERNS:
            if re.search(pat, c.text):
                res.violations.append({
                    "claim_id": c.claim_id, "rule": "因果表述",
                    "detail": f"出现因果词『{pat}』，样本数据只能支撑相关性表述",
                })
        if c.topic_sample_size is not None and c.topic_sample_size < SMALL_SAMPLE_N and SMALL_SAMPLE_MARK not in c.text:
            res.violations.append({
                "claim_id": c.claim_id, "rule": "小样本",
                "detail": f"主题样本量 {c.topic_sample_size} < {SMALL_SAMPLE_N}，须标注『小样本』",
            })
    res.passed = not res.violations
    return res
