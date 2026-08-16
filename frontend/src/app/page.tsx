"use client";

import { useEffect, useState } from "react";
import { data, setRunContext, getStoredRun, DEMO_MODE } from "@/lib/api";
import type { RunSummary } from "@/lib/types";
import {
  Badge, Button, Card, CardBody, CardHeader, CardTitle, CardDesc,
  Empty, ScopeNote, Table, Td, Th,
} from "@/components/ui";

const STAGE_LABELS: Record<string, string> = {
  normalize: "规范化", relevance_filter: "相关性预筛", embed_cluster: "向量聚类",
  annotate_cheap: "低成本标注", route_review: "复核路由", annotate_strong: "强模型复核",
  await_human: "人工审核", aggregate: "量化聚合", report: "报告生成", verify: "结论验证",
};

export default function DataPage() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stages, setStages] = useState<Record<string, string>>({});

  useEffect(() => {
    setSelected(getStoredRun());
    if (!DEMO_MODE) {
      data.runs().then(setRuns).catch((e) => setError(String(e.message)));
    }
  }, []);

  const choose = async (rid: string) => {
    setSelected(rid);
    setRunContext(rid);
    try {
      const d = await data.runDetail(rid);
      const m = d.manifest as { stage_states?: Record<string, { status: string }> };
      setStages(Object.fromEntries(Object.entries(m.stage_states || {}).map(([k, v]) => [k, v.status])));
    } catch { /* ignore */ }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div>
        <h1 className="text-base font-semibold">数据与任务</h1>
        <p className="text-xs text-zinc-500">
          导入评论数据（CSV/XLSX/JSON/JSONL）→ 字段映射 → 创建分析任务；单机串行执行，支持阶段级断点续跑。
        </p>
      </div>
      <ScopeNote text="全部结论口径：所采样的 B 站讨论。导入数据最少需要 text / published_at / source_url 三个字段。" />

      {DEMO_MODE ? (
        <Card>
          <CardHeader><CardTitle>公开演示模式</CardTitle>
            <CardDesc>只读预计算数据，无密钥、无导入入口。本地完整模式请运行 scripts/start-local.ps1。</CardDesc>
          </CardHeader>
          <CardBody className="text-xs text-zinc-600">
            演示数据包含《原神》6.8 与《鸣潮》3.5 两个版本案例：受未登录会话限制，采集为
            「每视频首页评论 + 楼中楼」的受限公开采样，页面各处均展示该口径与样本量。
          </CardBody>
        </Card>
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle>任务列表</CardTitle>
              <CardDesc>选择任务后，其余页面展示该任务结果</CardDesc>
            </CardHeader>
            <CardBody>
              {error && <div className="mb-2 text-xs text-red-600">后端未启动或不可达：{error}</div>}
              {runs.length === 0 && !error && <Empty>暂无任务 —— 可通过 API 或 CLI 创建</Empty>}
              <Table>
                <thead>
                  <tr><Th>任务</Th><Th>研究</Th><Th>状态</Th><Th>模型</Th><Th /></tr>
                </thead>
                <tbody>
                  {runs.map((r) => (
                    <tr key={r.run_id} data-run={r.run_id}>
                      <Td className="font-mono text-[11px]">{r.run_id}</Td>
                      <Td>{r.study_id}</Td>
                      <Td>
                        <Badge tone={r.status === "completed" ? "green" : r.status === "failed" ? "red" : "amber"}>
                          {r.status}
                        </Badge>
                      </Td>
                      <Td className="text-zinc-500">{Object.values(r.models || {}).join(" / ")}</Td>
                      <Td>
                        <Button size="sm" variant={selected === r.run_id ? "default" : "outline"}
                          onClick={() => choose(r.run_id)}>
                          {selected === r.run_id ? "当前" : "查看"}
                        </Button>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </CardBody>
          </Card>

          {selected && Object.keys(stages).length > 0 && (
            <Card>
              <CardHeader><CardTitle>阶段进度（断点状态）</CardTitle></CardHeader>
              <CardBody className="grid grid-cols-2 gap-2 md:grid-cols-5">
                {Object.entries(stages).map(([k, v]) => (
                  <div key={k} className="rounded border border-zinc-100 p-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs">{STAGE_LABELS[k] ?? k}</span>
                      <Badge tone={v === "done" ? "green" : v === "failed" ? "red" : "amber"}>{v}</Badge>
                    </div>
                  </div>
                ))}
              </CardBody>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
