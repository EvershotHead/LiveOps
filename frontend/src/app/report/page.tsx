"use client";

import { useEffect, useState } from "react";
import { data, DEMO_MODE, type MetricsLike } from "@/lib/api";
import { Badge, Button, Card, CardBody, CardHeader, CardTitle, CardDesc, Empty, ScopeNote } from "@/components/ui";

export default function ReportPage() {
  const [url, setUrl] = useState<string | null>(null);
  const [claims, setClaims] = useState<{ claim_id: string; text: string; metric_ids: string[]; evidence_ids: string[] }[]>([]);
  const [verify, setVerify] = useState<{ passed: boolean; violations: unknown[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    try { setUrl(data.reportUrl()); } catch (e) { setErr(String(e)); }
    if (!DEMO_MODE) {
      data.metrics().then((m: MetricsLike) => {
        setClaims(m.claims ?? []);
        setVerify(m.verify_result ?? null);
      }).catch(() => { /* metrics 可选 */ });
    } else {
      data.metrics().then((m: MetricsLike) => setClaims(m.claims ?? [])).catch(() => { });
    }
  }, []);

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h1 className="text-base font-semibold">运营报告</h1>
          <p className="text-xs text-zinc-500">版本亮点 / 主要问题 / 社区诉求 / 建议动作 / 证据 / 局限性</p>
        </div>
        {verify && (
          <Badge tone={verify.passed ? "green" : "red"}>
            结论验证{verify.passed ? "通过" : "未通过"}
          </Badge>
        )}
      </div>

      <ScopeNote text="每条结论引用指标 ID 与证据 ID；验证节点未通过时不允许导出。报告使用浏览器打印为 PDF。" />

      {err && <Empty>报告未生成：{err}（需任务完成且结论验证通过）</Empty>}

      {claims.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>结论清单（程序化生成，LLM 不参与数值）</CardTitle>
            <CardDesc>每条含 metric 引用与 evidence 引用</CardDesc>
          </CardHeader>
          <CardBody className="space-y-2">
            {claims.map((c) => (
              <div key={c.claim_id} data-claim={c.claim_id} className="rounded border border-zinc-100 p-2.5">
                <p className="text-xs leading-5">{c.text}</p>
                <p className="mt-1 font-mono text-[10px] text-zinc-400">
                  metrics: {c.metric_ids.join(", ")} · evidence: {c.evidence_ids.join(", ")}
                </p>
              </div>
            ))}
          </CardBody>
        </Card>
      )}

      {url && (
        <Card>
          <CardHeader>
            <CardTitle>完整报告</CardTitle>
            <CardDesc>在新窗口打开后 Ctrl+P 打印为 PDF（打印样式已内置）</CardDesc>
          </CardHeader>
          <CardBody>
            <a href={url} target="_blank" rel="noreferrer">
              <Button>打开报告 HTML ↗</Button>
            </a>
          </CardBody>
        </Card>
      )}
    </div>
  );
}
