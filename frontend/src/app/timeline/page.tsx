"use client";

import { useEffect, useState } from "react";
import { data } from "@/lib/api";
import type { TimelineData } from "@/lib/types";
import { EChart } from "@/components/charts/echart";
import { Card, CardBody, CardHeader, CardTitle, CardDesc, Empty, ScopeNote } from "@/components/ui";

const PHASES = [
  { name: "预热期", from: -7, to: -1, color: "rgba(59,130,246,0.06)" },
  { name: "上线期", from: 0, to: 7, color: "rgba(16,185,129,0.08)" },
  { name: "发酵期", from: 8, to: 28, color: "rgba(245,158,11,0.07)" },
];

export default function TimelinePage() {
  const [d, setD] = useState<TimelineData | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    data.timeline().then(setD).catch((e) => setErr(String(e.message)));
  }, []);

  if (err) return <Empty>加载失败：{err}</Empty>;
  if (!d) return <Empty>加载中…</Empty>;

  const topics = Object.entries(d.topics).sort((a, b) => {
    const sa = b[1].daily_counts.reduce((x, y) => x + y, 0);
    const sb = a[1].daily_counts.reduce((x, y) => x + y, 0);
    return sa - sb;
  }).slice(0, 8);

  const days = Array.from({ length: 36 }, (_, i) => i - 7);

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div>
        <h1 className="text-base font-semibold">版本时间线</h1>
        <p className="text-xs text-zinc-500">以 T0（{d.t0}）为中心的相对时间 · 主题讨论量与趋势速度</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>主题讨论量（每日新增，Top8 主题）</CardTitle>
          <CardDesc>背景色带为预热 / 上线 / 发酵三段窗口</CardDesc>
        </CardHeader>
        <CardBody>
          <EChart
            dataCount={topics.length}
            height={360}
            option={{
              legend: { type: "scroll", bottom: 0, textStyle: { fontSize: 10 } },
              xAxis: {
                type: "category", data: days.map(String),
                name: "T+n",
                axisLabel: { interval: 3 },
              },
              yAxis: { type: "value", name: "评论数" },
              series: topics.map(([name, t]) => ({
                name, type: "line", smooth: true, symbol: "none",
                data: t.daily_counts, emphasis: { focus: "series" },
              })),
              dataZoom: [{ type: "inside" }],
            }}
          />
        </CardBody>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>趋势速度排行</CardTitle>
            <CardDesc>每日新增线性回归斜率 / 全期均值（无量纲）· 正值上升</CardDesc>
          </CardHeader>
          <CardBody>
            <EChart
              dataCount={topics.length}
              height={280}
              option={{
                xAxis: { type: "value" },
                yAxis: { type: "category", data: topics.map(([n]) => n).reverse() },
                series: [{
                  type: "bar",
                  data: topics.map(([, t]) => t.trend_speed ?? 0).reverse(),
                  itemStyle: { color: (p) => (Number(p.value) >= 0 ? "#059669" : "#dc2626") },
                }],
                grid: { left: 8, right: 16, top: 8, bottom: 4, containLabel: true },
              }}
            />
          </CardBody>
        </Card>

        <Card>
          <CardHeader><CardTitle>三段窗口结构</CardTitle>
            <CardDesc>各主题在预热/上线/发酵期的讨论分布（堆叠）</CardDesc>
          </CardHeader>
          <CardBody>
            <EChart
              dataCount={topics.length}
              height={280}
              option={{
                tooltip: { trigger: "axis" },
                legend: { bottom: 0, textStyle: { fontSize: 10 } },
                xAxis: { type: "category", data: topics.map(([n]) => n), axisLabel: { interval: 0, rotate: 30, fontSize: 10 } },
                yAxis: { type: "value" },
                series: PHASES.map((ph) => ({
                  name: ph.name, type: "bar", stack: "total",
                  data: topics.map(([, t]) =>
                    t.daily_counts.slice(ph.from - -7, ph.to - -7 + 1).reduce((a, b) => a + b, 0)),
                })),
                grid: { left: 8, right: 8, top: 24, bottom: 56, containLabel: true },
              }}
            />
          </CardBody>
        </Card>
      </div>

      <ScopeNote text={d.scope_statement} />
    </div>
  );
}
