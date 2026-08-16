"use client";

import { useEffect, useMemo, useState } from "react";
import { data } from "@/lib/api";
import type { Overview } from "@/lib/types";
import { EChart } from "@/components/charts/echart";
import {
  Badge, Card, CardBody, CardHeader, CardTitle, CardDesc, Empty, ScopeNote,
  Table, Td, Th, Tabs,
} from "@/components/ui";
import { GAME_NAMES } from "@/lib/nav";
import { num, pct, signed } from "@/lib/utils";

type TopicDetail = {
  topic: string;
  count: number;
  topic_share: number | null;
  net_support_rate: number | null;
  controversy: number;
  persistence: number;
  engagement_raw: number;
  video_count: number;
  trend_speed: number | null;
  stance: Record<string, number>;
};

export default function TopicsPage() {
  const [ov, setOv] = useState<Overview | null>(null);
  const [detail, setDetail] = useState<Record<string, TopicDetail> | null>(null);
  const [stanceFilter, setStanceFilter] = useState("all");
  const [gameFilter, setGameFilter] = useState("all");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([data.overview(), data.metrics()]).then(([o, m]) => {
      setOv(o as Overview);
      setDetail((m as { topics: Record<string, TopicDetail> }).topics);
    }).catch((e) => setErr(String(e.message)));
  }, []);

  const rows = useMemo(() => {
    if (!detail) return [];
    return Object.entries(detail)
      .map(([topic, t]) => ({ ...t, topic }))
      .filter((t) => (stanceFilter === "all" ? true :
        stanceFilter === "negative" ? (t.net_support_rate ?? 0) < 0 :
        stanceFilter === "positive" ? (t.net_support_rate ?? 0) > 0 : true))
      .filter((t) => (gameFilter === "all" ? true : true)) // 单任务研究，占位保筛选联动
      .sort((a, b) => b.count - a.count);
  }, [detail, stanceFilter, gameFilter]);

  if (err) return <Empty>加载失败：{err}</Empty>;
  if (!ov || !detail) return <Empty>加载中…</Empty>;

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-base font-semibold">主题洞察</h1>
          <p className="text-xs text-zinc-500">
            {GAME_NAMES[ov.study.game]} {ov.study.version} · 12 固定主题 + 新兴主题候选
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            aria-label="立场筛选"
            value={stanceFilter}
            onChange={(e) => setStanceFilter(e.target.value)}
            className="h-7 rounded-md border border-zinc-300 bg-white px-2 text-xs"
          >
            <option value="all">全部立场</option>
            <option value="negative">净支持率为负</option>
            <option value="positive">净支持率为正</option>
          </select>
          <select
            aria-label="范围筛选"
            value={gameFilter}
            onChange={(e) => setGameFilter(e.target.value)}
            className="h-7 rounded-md border border-zinc-300 bg-white px-2 text-xs"
          >
            <option value="all">全部视频类型</option>
            <option value="official">官方物料</option>
            <option value="fanwork">二创内容</option>
          </select>
        </div>
      </div>

      <Card>
        <CardHeader><CardTitle>主题 × 核心指标矩阵</CardTitle>
          <CardDesc>过滤后 {rows.length} 个主题 · 指标全部由 Python 计算</CardDesc>
        </CardHeader>
        <CardBody className="p-0">
          <Table>
            <thead>
              <tr>
                <Th>主题</Th><Th>样本</Th><Th>占比</Th><Th>净支持率</Th><Th>争议度</Th>
                <Th>持续性</Th><Th>互动(raw)</Th><Th>视频覆盖</Th><Th>趋势</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.topic} data-topic={t.topic}>
                  <Td className="font-medium">{t.topic}</Td>
                  <Td className="tabular-nums">{num(t.count)}</Td>
                  <Td className="tabular-nums">{pct(t.topic_share)}</Td>
                  <Td className={"tabular-nums " + ((t.net_support_rate ?? 0) < 0 ? "text-red-600" : "text-emerald-700")}>
                    {signed(t.net_support_rate)}
                  </Td>
                  <Td className="tabular-nums">{t.controversy.toFixed(2)}</Td>
                  <Td className="tabular-nums">{t.persistence.toFixed(2)}</Td>
                  <Td className="tabular-nums">{t.engagement_raw.toFixed(2)}</Td>
                  <Td className="tabular-nums">{t.video_count}</Td>
                  <Td className={"tabular-nums " + ((t.trend_speed ?? 0) >= 0 ? "text-emerald-700" : "text-red-600")}>
                    {t.trend_speed == null ? "—" : t.trend_speed.toFixed(2)}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </CardBody>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>净支持率对比</CardTitle></CardHeader>
          <CardBody>
            <EChart
              dataCount={rows.length}
              height={300}
              option={{
                xAxis: { type: "value", min: -1, max: 1 },
                yAxis: { type: "category", data: rows.map((r) => r.topic).reverse() },
                series: [{
                  type: "bar",
                  data: rows.map((r) => r.net_support_rate ?? 0).reverse(),
                  itemStyle: { color: (p) => (Number(p.value) >= 0 ? "#059669" : "#dc2626") },
                }],
                grid: { left: 8, right: 16, top: 8, bottom: 4, containLabel: true },
              }}
            />
          </CardBody>
        </Card>
        <Card>
          <CardHeader><CardTitle>持续性 × 争议度散点</CardTitle>
            <CardDesc>右上角 = 高争议且持续久的议题</CardDesc>
          </CardHeader>
          <CardBody>
            <EChart
              dataCount={rows.length}
              height={300}
              option={{
                xAxis: { type: "value", name: "持续性" },
                yAxis: { type: "value", name: "争议度" },
                series: [{
                  type: "scatter",
                  data: rows.map((r) => [r.persistence, r.controversy, r.topic]),
                  label: { show: true, formatter: (p) => String(Array.isArray(p.data) ? p.data[2] : ""), fontSize: 10, position: "top" },
                  symbolSize: 10,
                }],
                grid: { left: 8, right: 16, top: 24, bottom: 24, containLabel: true },
              }}
            />
          </CardBody>
        </Card>
      </div>

      <ScopeNote text={`${ov.scope_statement}。新兴主题（new:*）为聚类候选，人工命名前不进入结论。`} />
    </div>
  );
}
