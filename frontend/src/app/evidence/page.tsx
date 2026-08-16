"use client";

import { useCallback, useEffect, useState } from "react";
import { data, DEMO_MODE, getStoredRun } from "@/lib/api";
import type { ReviewItem } from "@/lib/types";
import {
  Badge, Button, Card, CardBody, CardHeader, CardTitle, CardDesc, Empty,
  Input, Label, ScopeNote, Separator,
} from "@/components/ui";

const STANCES = ["支持", "反对", "中立", "混合", "不明确"];
const EMOTIONS = ["喜悦", "期待", "惊讶", "失望", "愤怒", "焦虑", "调侃玩梗", "无明显情绪"];
const STAGE_TONE: Record<string, "blue" | "amber" | "green"> = {
  cheap: "blue", strong: "amber", human: "green",
};

export default function EvidencePage() {
  const [queue, setQueue] = useState<ReviewItem[]>([]);
  const [idx, setIdx] = useState(0);
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const runId = getStoredRun();

  const load = useCallback(() => {
    if (DEMO_MODE || !runId) return;
    data.reviewQueue(runId, 100).then((d: { count: number; items: ReviewItem[] }) => {
      setQueue(d.items);
    }).catch((e) => setErr(String(e.message)));
  }, [runId]);

  useEffect(load, [load]);

  if (DEMO_MODE) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <h1 className="text-base font-semibold">证据与审核</h1>
        <Card>
          <CardBody className="text-xs text-zinc-600">
            演示模式为只读：证据片段在「社区争议」「运营报告」页内联展示（含来源链接、模型标签、置信度、
            是否人工修正）。标注工作台（键盘流复核种子标注、修改留痕）在本地模式开放。
          </CardBody>
        </Card>
        <ScopeNote text="演示数据已匿名化：不含用户名、头像、UID；@提及与联系方式已脱敏。" />
      </div>
    );
  }

  if (err) return <Empty>加载失败：{err}</Empty>;
  if (!runId) return <Empty>请先在「数据与任务」页选择一个任务</Empty>;
  if (queue.length === 0) return <Empty>审核队列为空（任务可能未完成或已全部复核）</Empty>;

  const item = queue[idx % queue.length];
  const cur = item.current as Record<string, unknown>;

  const submit = async (changes: { field: string; after: unknown }[]) => {
    setMsg(null);
    try {
      const r = await fetch(
        `http://localhost:8000/api/review/${runId}/submit`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ post_id: item.post_id, changes, reviewer: "local-user", reason }),
        },
      );
      if (!r.ok) {
        const e = await r.json().catch(() => ({ detail: r.statusText }));
        setMsg(`❌ ${e.detail ?? "提交失败"}`);
        return;
      }
      setMsg("✅ 已记录");
      setReason("");
      setIdx((i) => i + 1);
      load();
    } catch (e) {
      setMsg(`❌ ${String(e)}`);
    }
  };

  const setStance = (s: string) => submit([{ field: "stance", after: s }]);
  const accept = () => submit([]);

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-base font-semibold">证据与审核（标注工作台）</h1>
          <p className="text-xs text-zinc-500">
            队列 {queue.length} 条 · 当前第 {idx + 1} 条 · 与模型建议不同时必须填修改原因
          </p>
        </div>
      </div>

      <Card data-review-card={item.post_id}>
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle className="text-xs font-normal text-zinc-500">
              <a href={item.video_url} target="_blank" rel="noreferrer" className="text-blue-600 underline">
                {item.video_title}
              </a>
              {item.parent_id ? " · 楼中楼" : ""}
            </CardTitle>
          </div>
          <div className="flex items-center gap-1.5">
            <Badge tone={STAGE_TONE[String(cur.stage)] ?? "gray"}>{String(cur.stage)}</Badge>
            <Badge tone="gray">置信度 {Number(cur.confidence).toFixed(2)}</Badge>
            {item.human_modified && <Badge tone="green">已人工修正</Badge>}
          </div>
        </CardHeader>
        <CardBody className="space-y-3">
          <blockquote className="rounded-md border-l-2 border-zinc-300 bg-zinc-50 px-3 py-2 text-sm leading-6">
            {item.text}
          </blockquote>
          <div className="flex flex-wrap gap-1.5 text-[11px]">
            <Badge>{String(cur.stance ?? "未标注")}</Badge>
            <Badge tone="gray">{String(cur.emotion ?? "—")}</Badge>
            <Badge tone="gray">反讽:{String(cur.irony)}</Badge>
            {(cur.topics as string[])?.map((t) => <Badge key={t} tone="blue">{t}</Badge>)}
            <Badge tone="gray">👍 {item.likes}</Badge>
          </div>

          <Separator />

          <div className="space-y-2">
            <Label>人工复核 —— 点击立场即提交（与建议不同需先填原因）</Label>
            <div className="flex flex-wrap gap-1.5">
              {STANCES.map((s) => (
                <Button key={s} size="sm" variant={cur.stance === s ? "default" : "outline"}
                  onClick={() => setStance(s)} data-stance={s}>
                  {s}
                </Button>
              ))}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {EMOTIONS.slice(0, 4).map((s) => (
                <Badge key={s} tone="gray">{s}（API 支持）</Badge>
              ))}
            </div>
            <Input placeholder="修改原因（与模型建议不同时必填）" value={reason}
              onChange={(e) => setReason(e.target.value)} />
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={accept}>✓ 接受模型标签（跳到下一条）</Button>
              <Button size="sm" variant="ghost" onClick={() => setIdx((i) => i + 1)}>跳过</Button>
            </div>
            {msg && <div className="text-xs">{msg}</div>}
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader><CardTitle>键盘流</CardTitle></CardHeader>
        <CardBody className="text-xs text-zinc-500">
          立场按钮支持焦点 + 回车；全字段（主题/情绪/反讽/意图/问题性质）修改经
          <code className="mx-1 rounded bg-zinc-100 px-1">POST /api/review/[run]/submit</code>
          提交，全部修改以字段级 diff 留痕（human_overrides.jsonl），可审计回放。
        </CardBody>
      </Card>

      <ScopeNote text="原文片段为匿名化数据；来源链接指向公开视频页。" />
    </div>
  );
}
