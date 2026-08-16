"use client";

import { useEffect, useState } from "react";
import { data, DEMO_MODE } from "@/lib/api";
import type { CompareData } from "@/lib/types";
import { EChart } from "@/components/charts/echart";
import {
  Card, CardBody, CardHeader, CardTitle, CardDesc, Empty, Input, ScopeNote, Table, Td, Th, Button,
} from "@/components/ui";
import { GAME_NAMES } from "@/lib/nav";
import { num, signed } from "@/lib/utils";

export default function ComparePage() {
  const [d, setD] = useState<CompareData | null>(null);
  const [runA, setRunA] = useState("");
  const [runB, setRunB] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const load = (a: string, b: string) => {
    if (!a || !b) return;
    data.compareRuns(a, b).then(setD).catch((e) => setErr(String(e.message)));
  };

  useEffect(() => {
    if (DEMO_MODE) {
      data.compare().then(setD).catch((e) => setErr(String(e.message)));
    }
  }, []);

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div>
        <h1 className="text-base font-semibold">双游戏对照</h1>
        <p className="text-xs text-zinc-500">相同相对时间窗（各自 T0 归一化）· 归一化指标 · 不输出胜负结论</p>
      </div>

      {!DEMO_MODE && (
        <Card>
          <CardBody className="flex flex-wrap items-end gap-2">
            <div className="min-w-56 flex-1">
              <label className="text-xs text-zinc-500" htmlFor="runA">任务 A（原神）</label>
              <Input id="runA" value={runA} onChange={(e) => setRunA(e.target.value)} placeholder="run_id A" />
            </div>
            <div className="min-w-56 flex-1">
              <label className="text-xs text-zinc-500" htmlFor="runB">任务 B（鸣潮）</label>
              <Input id="runB" value={runB} onChange={(e) => setRunB(e.target.value)} placeholder="run_id B" />
            </div>
            <Button onClick={() => load(runA.trim(), runB.trim())}>对照</Button>
          </CardBody>
        </Card>
      )}

      {err && <Empty>加载失败：{err}</Empty>}
      {!d && !err && !DEMO_MODE && <Empty>输入两个 run_id 进行对照</Empty>}
      {!d && DEMO_MODE && !err && <Empty>加载中…</Empty>}

      {d && (
        <>
          <div className="grid grid-cols-2 gap-3">
            {(["a", "b"] as const).map((side) => (
              <Card key={side}>
                <CardBody className="py-3">
                  <div className="text-sm font-semibold">
                    {GAME_NAMES[d[side].game] ?? d[side].game} {d[side].version}
                  </div>
                  <div className="mt-1 text-[11px] text-zinc-500">
                    T0 {d[side].t0} · 有效评论 {num(d[side].dataset.relevant_posts)} · 视频 {num(d[side].dataset.videos)}
                  </div>
                </CardBody>
              </Card>
            ))}
          </div>

          <ScopeNote text={d.sample_difference_note} />

          <Card>
            <CardHeader>
              <CardTitle>主题强度对照（每千条有效评论）</CardTitle>
              <CardDesc>归一化口径消除样本量差异</CardDesc>
            </CardHeader>
            <CardBody>
              <EChart
                dataCount={d.topic_rows.length}
                height={360}
                option={{
                  legend: { bottom: 0, textStyle: { fontSize: 10 } },
                  xAxis: { type: "category", data: d.topic_rows.map((r) => r.topic), axisLabel: { interval: 0, rotate: 30, fontSize: 10 } },
                  yAxis: { type: "value", name: "每千条" },
                  series: [
                    {
                      name: `${GAME_NAMES[d.a.game]} ${d.a.version}`, type: "bar",
                      data: d.topic_rows.map((r) => r.a_per_1000 ?? 0),
                      itemStyle: { color: "#e11d48" },
                    },
                    {
                      name: `${GAME_NAMES[d.b.game]} ${d.b.version}`, type: "bar",
                      data: d.topic_rows.map((r) => r.b_per_1000 ?? 0),
                      itemStyle: { color: "#2563eb" },
                    },
                  ],
                  grid: { left: 8, right: 8, top: 24, bottom: 72, containLabel: true },
                }}
              />
            </CardBody>
          </Card>

          <Card>
            <CardHeader><CardTitle>逐主题明细</CardTitle>
              <CardDesc>净支持率与争议度并列展示，不做加总排名</CardDesc>
            </CardHeader>
            <CardBody className="p-0">
              <Table>
                <thead>
                  <tr>
                    <Th>主题</Th>
                    <Th>A 每千条</Th><Th>B 每千条</Th>
                    <Th>A 净支持</Th><Th>B 净支持</Th>
                    <Th>A 争议</Th><Th>B 争议</Th>
                  </tr>
                </thead>
                <tbody>
                  {d.topic_rows.map((r) => (
                    <tr key={r.topic} data-topic={r.topic}>
                      <Td>{r.topic}</Td>
                      <Td className="tabular-nums">{r.a_per_1000 ?? "—"}</Td>
                      <Td className="tabular-nums">{r.b_per_1000 ?? "—"}</Td>
                      <Td className="tabular-nums">{signed(r.a_net_support)}</Td>
                      <Td className="tabular-nums">{signed(r.b_net_support)}</Td>
                      <Td className="tabular-nums">{r.a_controversy?.toFixed(2) ?? "—"}</Td>
                      <Td className="tabular-nums">{r.b_controversy?.toFixed(2) ?? "—"}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </CardBody>
          </Card>

          <ScopeNote text={d.disclaimer} />
        </>
      )}
    </div>
  );
}
