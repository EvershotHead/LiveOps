"use client";

import { useEffect, useState } from "react";
import { data } from "@/lib/api";
import type { ControversyRow, EvidenceItem } from "@/lib/types";
import { EChart } from "@/components/charts/echart";
import {
  Badge, Card, CardBody, CardHeader, CardTitle, CardDesc, Empty, ScopeNote, Table, Td, Th,
} from "@/components/ui";
import { STANCE_COLORS } from "@/lib/nav";
import { signed } from "@/lib/utils";

export default function ControversyPage() {
  const [rows, setRows] = useState<ControversyRow[]>([]);
  const [scope, setScope] = useState("");
  const [evCache, setEvCache] = useState<Record<string, EvidenceItem>>({});
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    data.controversy().then((d: { rows: ControversyRow[]; scope_statement: string }) => {
      setRows(d.rows);
      setScope(d.scope_statement);
    }).catch((e) => setErr(String(e.message)));
  }, []);

  const loadEvidence = async (id: string) => {
    if (evCache[id]) return;
    try {
      const e = await data.evidence("", id);
      setEvCache((c) => ({ ...c, [id]: e as EvidenceItem }));
    } catch { /* 证据可能已归档 */ }
  };

  if (err) return <Empty>加载失败：{err}</Empty>;
  if (rows.length === 0) return <Empty>加载中…</Empty>;

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div>
        <h1 className="text-base font-semibold">社区争议</h1>
        <p className="text-xs text-zinc-500">冲突话题排序：0.5×立场熵 + 0.3×楼中楼对立 + 0.2×讨论量归一</p>
      </div>

      {rows.map((r) => (
        <Card key={r.topic} data-topic={r.topic}>
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle>{r.topic}</CardTitle>
              <CardDesc>
                争议度 {r.controversy.toFixed(2)} · 楼中楼对立率 {r.reply_conflict == null ? "—" : `${(r.reply_conflict * 100).toFixed(0)}%`}
                {" "}· 净支持率 {signed(r.net_support)}
              </CardDesc>
            </div>
            <Badge tone={r.reply_conflict != null && r.reply_conflict > 0.3 ? "red" : "amber"}>
              {r.reply_conflict != null && r.reply_conflict > 0.3 ? "高冲突" : "有分歧"}
            </Badge>
          </CardHeader>
          <CardBody className="grid gap-4 md:grid-cols-2">
            <EChart
              dataCount={Object.values(r.stance).reduce((a, b) => a + b, 0)}
              height={200}
              option={{
                tooltip: { trigger: "item" },
                series: [{
                  type: "pie", radius: ["36%", "62%"],
                  data: Object.entries(r.stance)
                    .filter(([, v]) => v > 0)
                    .map(([name, value]) => ({ name, value, itemStyle: { color: STANCE_COLORS[name] ?? "#a1a1aa" } })),
                  label: { formatter: "{b} {d}%", fontSize: 10 },
                }],
                graphic: [] as never[],
              }}
            />
            <div>
              <div className="mb-1.5 text-[11px] font-medium text-zinc-500">代表性证据（按立场）</div>
              <div className="space-y-1.5">
                {Object.entries(r.evidence).map(([stance, ids]) => (
                  <div key={stance} className="space-y-1">
                    {ids.map((id) => {
                      const e = evCache[id];
                      return (
                        <button
                          key={id}
                          onClick={() => loadEvidence(id)}
                          className="block w-full rounded border border-zinc-100 bg-zinc-50/60 px-2.5 py-1.5 text-left text-[11px] hover:border-zinc-300"
                          data-evidence-id={id}
                        >
                          <span className="font-medium" style={{ color: STANCE_COLORS[stance] }}>{stance}</span>
                          {" "}
                          <span className="text-zinc-700">
                            {e ? e.text_excerpt : `${id}（点击加载原文）`}
                          </span>
                          {e && (
                            <a
                              href={e.source_url}
                              target="_blank"
                              rel="noreferrer"
                              className="ml-1 text-blue-600 underline"
                              onClick={(ev) => ev.stopPropagation()}
                            >
                              来源
                            </a>
                          )}
                        </button>
                      );
                    })}
                  </div>
                ))}
              </div>
            </div>
          </CardBody>
        </Card>
      ))}

      <ScopeNote text={scope || "所采样的 B 站讨论"} />
    </div>
  );
}
