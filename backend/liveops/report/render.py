"""HTML 报告渲染（Jinja2）。打印为 PDF 走浏览器打印；LibreOffice 仅备选。"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FunctionLoader, select_autoescape

from ..evidence import EvidenceItem
from .verify import Claim

_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{{ metrics.game }} {{ metrics.version_label }} 版本社区复盘报告</title>
<style>
  :root { --ink:#1a1a1a; --sub:#666; --line:#e5e5e5; --bg:#fafafa; }
  * { box-sizing:border-box; }
  body { font:14px/1.7 "Microsoft YaHei",system-ui,sans-serif; color:var(--ink);
         max-width:900px; margin:24px auto; padding:0 20px; background:#fff; }
  h1 { font-size:22px; margin:0 0 4px; }
  h2 { font-size:16px; margin:28px 0 8px; border-left:3px solid #333; padding-left:8px; }
  .meta { color:var(--sub); font-size:12px; margin-bottom:16px; }
  .scope { background:var(--bg); border:1px solid var(--line); padding:8px 12px;
           font-size:12px; color:var(--sub); }
  table { border-collapse:collapse; width:100%; font-size:13px; margin:8px 0; }
  th,td { border:1px solid var(--line); padding:6px 8px; text-align:left; }
  th { background:var(--bg); font-weight:600; }
  .claim { border:1px solid var(--line); padding:10px 12px; margin:8px 0; }
  .claim .ids { color:var(--sub); font-size:12px; }
  .ev { font-size:12px; color:var(--sub); margin:4px 0 12px; padding-left:12px;
        border-left:2px solid var(--line); }
  .ev a { color:#0b57d0; text-decoration:none; word-break:break-all; }
  .warn { color:#b00; }
  footer { margin-top:32px; color:var(--sub); font-size:12px; border-top:1px solid var(--line); padding-top:8px; }
  @media print { body{margin:0} .noprint{display:none} }
</style>
</head>
<body>
<h1>{{ metrics.game }} {{ metrics.version_label }} 版本社区复盘报告</h1>
<div class="meta">
  数据口径：T0={{ metrics.t0_date }}，窗口 T-7 ~ T+28 ·
  有效相关评论 {{ metrics.dataset.relevant_posts }} 条 / {{ metrics.dataset.videos }} 个视频
</div>
<div class="scope">口径声明：本报告全部结论仅描述<b>所采样的 B 站讨论</b>，不代表所有玩家。
组合分数为可配置的运营排序规则，非客观事实；分项与权重敏感性见附录。</div>

<h2>一、版本亮点（正向机会）</h2>
{% for c in claims if c.claim_id.startswith("opp-") %}
<div class="claim">{{ c.text }}<div class="ids">metrics: {{ c.metric_ids|join(", ") }}</div></div>
{% for eid in c.evidence_ids %}{% set e = evidence.get(eid) %}{% if e %}
<div class="ev">【{{ e.stance or "未标注" }}｜{{ e.emotion or "-" }}】{{ e.text_excerpt }}…
<a href="{{ e.source_url }}">来源</a>（{{ e.video_title }}）置信度 {{ e.confidence }}</div>
{% endif %}{% endfor %}
{% endfor %}

<h2>二、主要问题（运营优先级 Top3）</h2>
{% for c in claims if c.claim_id.startswith("issue-") %}
<div class="claim">{{ c.text }}<div class="ids">metrics: {{ c.metric_ids|join(", ") }}</div></div>
{% for eid in c.evidence_ids %}{% set e = evidence.get(eid) %}{% if e %}
<div class="ev">【{{ e.stance or "未标注" }}｜{{ e.emotion or "-" }}】{{ e.text_excerpt }}…
<a href="{{ e.source_url }}">来源</a>（{{ e.video_title }}）置信度 {{ e.confidence }}</div>
{% endif %}{% endfor %}
{% endfor %}

<h2>三、主题总览</h2>
<table>
<tr><th>主题</th><th>样本</th><th>占比</th><th>净支持率</th><th>争议度</th><th>视频覆盖</th><th>持续性</th></tr>
{% for t, ts in topics %}
<tr><td>{{ t }}</td><td>{{ ts.count }}</td>
<td>{% if ts.topic_share is not none %}{{ "%.1f"|format(ts.topic_share*100) }}%{% else %}-{% endif %}</td>
<td>{% if ts.net_support_rate is not none %}{{ "%+.2f"|format(ts.net_support_rate) }}{% else %}-{% endif %}</td>
<td>{{ "%.2f"|format(ts.controversy) }}</td><td>{{ ts.video_count }}</td>
<td>{{ "%.2f"|format(ts.persistence) }}</td></tr>
{% endfor %}
</table>

<h2>四、组合分数与权重</h2>
<table>
<tr><th>类型</th><th>权重</th></tr>
<tr><td>运营问题优先级</td><td>{{ weights_issue }}</td></tr>
<tr><td>正向机会值</td><td>{{ weights_opp }}</td></tr>
</table>
<p class="scope">敏感性：±10% 权重扰动下主题排名最大变化
{% if sens_issue_max is not none %}{{ sens_issue_max }} 位{% else %}未计算（无主题）{% endif %}。
完整敏感性数据见 metrics.json。</p>

<h2>五、局限性</h2>
<ul>
<li>样本仅覆盖 B 站单平台所采样的视频评论区，平台受众有偏，不能外推到全体玩家。</li>
<li>弃权（无法判断）样本 {{ metrics.dataset.abstain_count }} 条未计入立场类指标。</li>
<li>趋势与持续性受采样时点影响；相关 ≠ 因果，本报告不使用因果表述。</li>
{% if metrics.embed_quality == "hash-degraded" %}
<li class="warn">嵌入模型降级运行（hash-degraded），主题先验与新兴主题聚类质量受限。</li>
{% endif %}
</ul>

<footer>LiveOps Community Intelligence · 生成于验证节点通过后 ·
组合分数权重可配置，本页数字由 Python 计算生成，LLM 不参与数值计算。</footer>
</body>
</html>"""


def render_report_html(metrics: dict, claims: list[Claim],
                       evidence: dict[str, EvidenceItem] | None = None) -> str:
    env = Environment(
        loader=FunctionLoader(lambda name: _TEMPLATE if name == "report" else None),
        autoescape=select_autoescape(["html"]),
    )
    tpl = env.get_template("report")
    sens = (metrics.get("composites", {}).get("sensitivity") or {}).get("issue")
    sens_max = None
    if sens and isinstance(sens, dict):
        shifts = [abs(v) for s in sens.get("scenarios", []) for v in s.get("rank_shift", {}).values()]
        sens_max = max(shifts) if shifts else 0
    return tpl.render(
        metrics=metrics,
        claims=claims,
        evidence={k: e for k, e in (evidence or {}).items()},
        topics=sorted(metrics.get("topics", {}).items(), key=lambda kv: -kv[1]["count"]),
        weights_issue=metrics["composites"]["issue_priority"]["weights"],
        weights_opp=metrics["composites"]["opportunity"]["weights"],
        sens_issue_max=sens_max,
    )
