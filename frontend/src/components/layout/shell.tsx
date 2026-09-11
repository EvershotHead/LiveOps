"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  Activity, BarChart3, CalendarRange, Database, FileText, FlaskConical,
  GitCompareArrows, MessagesSquare, SearchCheck, Menu,
} from "lucide-react";
import { DEMO_BRAND } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { DEMO_MODE } from "@/lib/api";
import { Badge } from "@/components/ui";
import { StudySwitcher } from "@/components/layout/study-switcher";

const NAV_GROUPS: { group: string; items: { href: string; label: string; icon: typeof Database }[] }[] = [
  {
    group: "决策台",
    items: [
      { href: "/", label: "数据与任务", icon: Database },
      { href: "/overview", label: "总览", icon: BarChart3 },
    ],
  },
  {
    group: "版本分析",
    items: [
      { href: "/timeline", label: "版本时间线", icon: CalendarRange },
      { href: "/topics", label: "主题洞察", icon: MessagesSquare },
      { href: "/controversy", label: "社区争议", icon: Activity },
    ],
  },
  {
    group: "跨版本",
    items: [{ href: "/compare", label: "双游戏对照", icon: GitCompareArrows }],
  },
  {
    group: "治理与质量",
    items: [
      { href: "/evidence", label: "证据与审核", icon: SearchCheck },
      { href: "/evaluation", label: "模型评测", icon: FlaskConical },
      { href: "/report", label: "运营报告", icon: FileText },
    ],
  },
];

const PAGE_TITLES: Record<string, string> = Object.fromEntries(
  NAV_GROUPS.flatMap((g) => g.items).map((n) => [n.href, n.label]),
);

export function Shell({ children, mode }: { children: React.ReactNode; mode: "local" | "demo" }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const title = PAGE_TITLES[pathname] ?? "";
  return (
    <div className="flex min-h-screen bg-zinc-50 text-zinc-900">
      {/* 侧边导航 */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 w-52 shrink-0 border-r border-zinc-200 bg-white md:static md:translate-x-0 transition-transform",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-12 items-center gap-2 border-b border-zinc-100 px-4">
          <span className="h-2 w-2 rounded-full bg-zinc-900" />
          <div>
            <div className="text-[13px] font-semibold leading-4">LiveOps CI</div>
            <div className="text-[10px] text-zinc-400">版本社区洞察工作台</div>
          </div>
        </div>
        <nav className="p-2" aria-label="主导航">
          {NAV_GROUPS.map((g) => (
            <div key={g.group} className="mb-1.5">
              <div className="px-2.5 pb-1 pt-1.5 text-[10px] font-medium uppercase tracking-wider text-zinc-400">
                {g.group}
              </div>
              {g.items.map((n) => {
                const Icon = n.icon;
                const active = pathname === n.href;
                return (
                  <Link
                    key={n.href}
                    href={n.href}
                    onClick={() => setOpen(false)}
                    data-nav={n.label}
                    className={cn(
                      "mb-0.5 flex items-center gap-2 rounded-md px-2.5 py-1.5 text-[13px]",
                      active ? "bg-zinc-100 font-medium text-zinc-900" : "text-zinc-600 hover:bg-zinc-50",
                    )}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {n.label}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="absolute bottom-0 left-0 right-0 border-t border-zinc-100 p-3">
          <Badge tone={mode === "demo" ? "blue" : "green"}>
            {mode === "demo" ? "公开演示 · 只读" : "本地模式"}
          </Badge>
          <p className="mt-2 text-[10px] leading-4 text-zinc-400">
            结论口径：所采样的 B 站讨论，不代表所有玩家。
          </p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* 顶栏：移动端品牌 + 菜单；桌面端页面标题 + study 切换器 */}
        <header className="sticky top-0 z-30 flex h-12 items-center gap-3 border-b border-zinc-200 bg-white/95 px-4 backdrop-blur">
          <button aria-label="菜单" onClick={() => setOpen(!open)} className="rounded p-1 hover:bg-zinc-100 md:hidden">
            <Menu className="h-5 w-5" />
          </button>
          <span className="text-sm font-semibold md:hidden">{DEMO_BRAND}</span>
          <h1 className="hidden text-[13px] font-medium text-zinc-500 md:block">{title}</h1>
          <div className="ml-auto flex items-center gap-2">
            {DEMO_MODE && <StudySwitcher />}
          </div>
        </header>
        <main className="min-w-0 flex-1 p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
