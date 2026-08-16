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
import { Badge } from "@/components/ui";

const NAV = [
  { href: "/", label: "数据与任务", icon: Database },
  { href: "/overview", label: "总览", icon: BarChart3 },
  { href: "/timeline", label: "版本时间线", icon: CalendarRange },
  { href: "/topics", label: "主题洞察", icon: MessagesSquare },
  { href: "/controversy", label: "社区争议", icon: Activity },
  { href: "/compare", label: "双游戏对照", icon: GitCompareArrows },
  { href: "/evidence", label: "证据与审核", icon: SearchCheck },
  { href: "/evaluation", label: "模型评测", icon: FlaskConical },
  { href: "/report", label: "运营报告", icon: FileText },
];

export function Shell({ children, mode }: { children: React.ReactNode; mode: "local" | "demo" }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
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
          {NAV.map((n) => {
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
        <header className="flex h-12 items-center gap-3 border-b border-zinc-200 bg-white px-4 md:hidden">
          <button aria-label="菜单" onClick={() => setOpen(!open)} className="rounded p-1 hover:bg-zinc-100">
            <Menu className="h-5 w-5" />
          </button>
          <span className="text-sm font-semibold">{DEMO_BRAND}</span>
        </header>
        <main className="min-w-0 flex-1 p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
