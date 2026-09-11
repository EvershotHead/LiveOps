"use client";

import { useEffect, useState } from "react";
import { DEMO_MODE, data } from "@/lib/api";
import type { Overview } from "@/lib/types";
import { EChart } from "@/components/charts/echart";
import {
  Badge, Card, CardBody, CardHeader, CardTitle, CardDesc, Empty, PageHeader,
  ScopeNote, StatCard, Table, Td, Th,
} from "@/components/ui";
import { GAME_NAMES, STANCE_COLORS } from "@/lib/nav";
import { num, pct, signed } from "@/lib/utils";
import { currentStudyId, getStudy, previousStudyOf } from "@/lib/studies";

type Delta = { label: string; value: number | null } | null;

function DeltaChip({ d }: { d: Delta }) {
  if (!d || d.value === null) return null;
  const up = d.value >= 0;
  return (
    <span
      className={
        "ml-1.5 inline-flex items-center gap-0.5 rounded px-1 py-px text-[10px] font-medium tabular-nums " +
        (up ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700")
      }
      title={`相对上一版本 ${d.label}`}
    >
      {up ? "▲" : "▼"} {Math.abs(d.value) < 1 ? Math.abs(d.value).toFixed(1) : num(Math.abs(d.value))}
    </span>
  );
}

export default function OverviewPage() {
  const [d, setD] = useState<Overview | null>(null);
  const [prev, setPrev] = useState<Overview | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    data.overview().then(setD).catch((e) => setErr(String(e.message)));
    if (DEMO_MODE) {
      const p = previousStudyOf(currentStudyId());
      if (p) fetch(`public-data/overview-${p.id}.json`).then((r) => (r.ok ? r.json() : null)).then((j) => j && setPrev(j)).catch(() => {});
    }
  }, []);

  if (err) return <Empty>加载失败：{err}</Empty>;
  if (!d) return <Empty>加载中…</Empty>;

  const meta = getStudy(d.study.study_id);
  const stance = d.overall.stance;
  const stanceData = [
    { name: "支持", value: stance.support }, { name: "反对", value: stance.oppose },
    { name: "中立", value: stance.neutral }, { name: "混合", value: stance.mixed },
    { name: "不明确", value: stance.unclear },
  ].filter((x) => x.value > 0);

  const net = d.overall.net_support_rate;
  const deltas: Record<string, Delta> = prev
    ? {
        relevant: { label: prev.study.version, value: d.dataset.relevant_posts - prev.dataset.relevant_posts },
        videos: { label: prev.study.version, value: d.dataset.videos - prev.dataset.videos },
        net: prev.overall.net_support_rate !== null && net !== null
          ? { label: prev.study.version, value: net - prev.overall.net_support_rate }
          : null,
      }
    : {};

  const lowSample = d.dataset.relevant_posts < 3000;

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <PageHeader
        title={`${GAME_NAMES[d.study.game] ?? d.study.game} ${d.study.version}${meta?.codename ? `「${meta.codename}」` : ""} · 社区总览`}
        desc={`T0 = ${d.study.t0} · 相对窗口 T-7 ~ T+28 · 所有结论可回溯到统计口径与代表性原文`}
        right={<Badge tone="gray">{d.scope_statement}</Badge>}
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <StatCard
          label="整体净支持率"
          tone={net === null ? "default" : net >= 0 ? "green" : "red"}
          value={signed(net)}
          sub={<span>相对上一版本<DeltaChip d={deltas.net ?? null} /></span>}
        />
        <StatCard
          label="有效相关评论"
          value={num(d.dataset.relevant_posts)}
          sub={<span>相对上一版本<DeltaChip d={deltas.relevant ?? null} /></span>}
        />
        <StatCard label="视频覆盖" value={num(d.dataset.videos)} sub={<span>相对上一版本<DeltaChip d={deltas.videos ?? null} /></span>} />
        <StatCard label="弃权样本" value={num(d.dataset.abstain_count)} sub="模型无法判断，如实计入弃权率" />
        <StatCard label="无关剔除" value={num(d.dataset.irrelevant_count)} sub="相关性过滤剔除" />
      </div>

      {lowSample && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] leading-5 text-amber-800">
          样本量口径提示：本版本有效相关评论低于方案目标（3,000 条/游戏）。采集受限与版本讨论热度都会影响样本量，
          解读时请关注趋势方向而非精确占比，详见报告页「局限性」。
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>主题分布</CardTitle>
            <CardDesc>占有效相关评论比例 · 点位见下表</CardDesc>
          </CardHeader>
          <CardBody>
            <EChart
              dataCount={d.topic_shares.length}
              option={{
                xAxis: { type: "value" },
                yAxis: { type: "category", data: d.topic_shares.map((t) => t.topic).reverse() },
                series: [{
                  type: "bar",
                  data: d.topic_shares.map((t) => t.share ?? 0).reverse(),
                  itemStyle: { color: "#3f3f46" },
                  label: { show: true, position: "right", formatter: (p) => pct(Number(p.value)) },
                }],
                grid: { left: 8, right: 48, top: 8, bottom: 4, containLabel: true },
              }}
              height={300}
            />
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>整体立场结构</CardTitle>
            <CardDesc>有立场标注样本的分布；净支持率 =（支持-反对）/（支持+反对）</CardDesc>
          </CardHeader>
          <CardBody>
            <EChart
              dataCount={stanceData.length}
              option={{
                tooltip: { trigger: "item" },
                series: [{
                  type: "pie", radius: ["42%", "70%"], center: ["50%", "50%"],
                  data: stanceData.map((x) => ({ ...x, itemStyle: { color: STANCE_COLORS[x.name] } })),
                  label: { formatter: "{b} {d}%" },
                }],
              }}
              height={300}
            />
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>运营风险清单（问题优先级 Top5）</CardTitle>
            <CardDesc>{d.disclaimer} · 分项与敏感性见各主题页</CardDesc>
          </CardHeader>
          <CardBody className="space-y-1.5">
            {d.top_risks.map((r, i) => (
              <div key={r.topic} className="flex items-center justify-between rounded border border-red-100 bg-red-50/50 px-2.5 py-1.5">
                <span className="text-xs">{i + 1}. {r.topic}</span>
                <span className="font-mono text-xs tabular-nums text-red-700">{r.score.toFixed(3)}</span>
              </div>
            ))}
          </CardBody>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>正向机会清单（机会值 Top5）</CardTitle>
            <CardDesc>支持率35% + 增长25% + 视频覆盖20% + 互动10% + 持续10%（可配置）</CardDesc>
          </CardHeader>
          <CardBody className="space-y-1.5">
            {d.top_opportunities.map((r, i) => (
              <div key={r.topic} className="flex items-center justify-between rounded border border-emerald-100 bg-emerald-50/50 px-2.5 py-1.5">
                <span className="text-xs">{i + 1}. {r.topic}</span>
                <span className="font-mono text-xs tabular-nums text-emerald-700">{r.score.toFixed(3)}</span>
              </div>
            ))}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>主题指标明细</CardTitle>
          <CardDesc>每个数字可回溯到统计口径与代表性证据（证据与审核页）</CardDesc>
        </CardHeader>
        <CardBody className="p-0">
          <Table>
            <thead>
              <tr><Th>主题</Th><Th>样本</Th><Th>占比</Th><Th>净支持率</Th><Th>争议度</Th></tr>
            </thead>
            <tbody>
              {d.topic_shares.map((t) => (
                <tr key={t.topic} className="hover:bg-zinc-50">
                  <Td>{t.topic}</Td>
                  <Td className="tabular-nums">{num(t.count)}</Td>
                  <Td className="tabular-nums">{pct(t.share)}</Td>
                  <Td className={"tabular-nums " + ((t.net_support ?? 0) < 0 ? "text-red-600" : "text-emerald-700")}>
                    {signed(t.net_support)}
                  </Td>
                  <Td className="tabular-nums">{t.controversy.toFixed(2)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </CardBody>
      </Card>

      <ScopeNote text={`组合分数为可配置的运营排序规则而非客观事实。当前权重：问题优先级 ${Object.entries(d.weights.issue_priority).map(([k, v]) => `${k}${(v * 100).toFixed(0)}%`).join(" / ")}。`} />
    </div>
  );
}
