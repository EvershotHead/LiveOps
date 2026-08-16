"use client";

import { useEffect, useState } from "react";
import { data } from "@/lib/api";
import type { EvaluationData } from "@/lib/types";
import { EChart } from "@/components/charts/echart";
import {
  Badge, Card, CardBody, CardHeader, CardTitle, CardDesc, Empty, ScopeNote, Table, Td, Th,
} from "@/components/ui";

const LAYER_LABEL: Record<string, string> = {
  strong_model_seed: "强模型种子层（开发 Agent 生成，第一层）",
  human: "人工金标层（用户复核，第二层）",
  mixed: "混合（人工覆盖优先）",
};

export default function EvaluationPage() {
  const [d, setD] = useState<EvaluationData | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    data.evaluation().then(setD).catch((e) => setErr(String(e.message)));
  }, []);

  if (err) return <Empty>评测数据未生成：{err}</Empty>;
  if (!d) return <Empty>加载中…</Empty>;

  const rows = [
    { name: "相关性", got: d.relevance?.macro_f1, target: d.targets.relevance },
    { name: "主题(多标签)", got: d.topics?.macro_f1, target: d.targets.topics },
    { name: "立场", got: d.stance?.macro_f1, target: d.targets.stance },
    { name: "情绪", got: d.emotion?.macro_f1, target: d.targets.emotion },
    { name: "反讽", got: d.irony?.macro_f1, target: d.targets.irony },
  ];

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-base font-semibold">模型评测</h1>
          <p className="text-xs text-zinc-500">
            金标 {d.n_gold} 条（评测 {d.n_evaluated} 条）· 分组切分（同视频不跨训练/测试）
          </p>
        </div>
        <Badge tone="blue">{LAYER_LABEL[d.gold_layer] ?? d.gold_layer}</Badge>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Macro-F1 vs 目标门槛</CardTitle>
          <CardDesc>目标：相关性≥0.90 · 主题≥0.70 · 立场≥0.75 · 情绪≥0.65 · 反讽≥0.60</CardDesc>
        </CardHeader>
        <CardBody>
          <Table>
            <thead>
              <tr><Th>维度</Th><Th>实测</Th><Th>目标</Th><Th>状态</Th></tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const measured = r.got != null;
                const pass = measured && r.got! >= r.target;
                return (
                  <tr key={r.name} data-metric={r.name}>
                    <Td className="font-medium">{r.name}</Td>
                    <Td className="tabular-nums">{measured ? r.got!.toFixed(3) : "未测量"}</Td>
                    <Td className="tabular-nums text-zinc-500">≥{r.target.toFixed(2)}</Td>
                    <Td>
                      {!measured ? <Badge tone="gray">未测量</Badge>
                        : pass ? <Badge tone="green">达标</Badge>
                        : <Badge tone="red">未达标</Badge>}
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        </CardBody>
      </Card>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader><CardTitle>置信度校准（ECE）</CardTitle></CardHeader>
          <CardBody>
            <div className="text-2xl font-semibold tabular-nums">
              {d.ece == null ? "未测量" : d.ece.toFixed(3)}
            </div>
            <p className="mt-1 text-[11px] text-zinc-500">10 桶 |acc−conf| 加权；越低越校准</p>
          </CardBody>
        </Card>
        <Card>
          <CardHeader><CardTitle>弃权率（反讽维度）</CardTitle></CardHeader>
          <CardBody>
            <div className="text-2xl font-semibold tabular-nums">
              {d.irony?.abstain_rate == null ? "未测量" : `${(d.irony.abstain_rate * 100).toFixed(1)}%`}
            </div>
            <p className="mt-1 text-[11px] text-zinc-500">允许弃权是特性：语境不足不强行二分</p>
          </CardBody>
        </Card>
        <Card>
          <CardHeader><CardTitle>成本与吞吐</CardTitle></CardHeader>
          <CardBody>
            <div className="text-2xl font-semibold tabular-nums">
              {d.cost_cny == null ? "未测量" : `¥${d.cost_cny.toFixed(2)}`}
            </div>
            <p className="mt-1 text-[11px] text-zinc-500">
              吞吐 {d.throughput_per_min == null ? "未测量" : `${d.throughput_per_min.toFixed(0)} 条/分`}
              {" "}· Kappa {d.kappa == null ? "（人工层到位后计算）" : d.kappa.toFixed(2)}
            </p>
          </CardBody>
        </Card>
      </div>

      {Object.entries(d.confusion).filter(([, cm]) => cm && cm.labels).map(([dim, cm]) => (
        <Card key={dim}>
          <CardHeader><CardTitle>混淆矩阵 · {dim}</CardTitle></CardHeader>
          <CardBody>
            <EChart
              dataCount={cm.matrix.length}
              height={Math.max(200, cm.labels.length * 28 + 80)}
              option={{
                tooltip: {},
                grid: { left: 90, right: 90, top: 10, bottom: 60 },
                xAxis: { type: "category", data: cm.labels, axisLabel: { rotate: 40, fontSize: 10 } },
                yAxis: { type: "category", data: cm.labels, axisLabel: { fontSize: 10 } },
                visualMap: {
                  min: 0, max: Math.max(1, ...cm.matrix.flat()), show: false,
                  inRange: { color: ["#fafafa", "#a1a1aa", "#3f3f46"] },
                },
                series: [{
                  type: "heatmap",
                  data: cm.matrix.flatMap((row, i) => row.map((v, j) => [j, i, v])),
                  label: { show: true, fontSize: 10 },
                }],
              }}
            />
          </CardBody>
        </Card>
      ))}

      {d.notes?.length > 0 && (
        <ScopeNote text={d.notes.join("；")} />
      )}
      <ScopeNote text="标签不足 1,500 条时不宣称完成可靠微调；当前为「LLM 结构化标注 + 向量基线 + 人工复核」模式。" />
    </div>
  );
}
