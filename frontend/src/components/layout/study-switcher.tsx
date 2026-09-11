"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import { STUDIES, currentStudyId, setStudyId, type StudyMeta } from "@/lib/studies";
import { cn } from "@/lib/utils";

const GAME_DOT: Record<string, string> = {
  genshin: "bg-amber-500",
  wuthering_waves: "bg-cyan-600",
};

function StudyRow({ s, active, onPick }: { s: StudyMeta; active: boolean; onPick: () => void }) {
  return (
    <button
      onClick={onPick}
      className={cn(
        "flex w-full items-center gap-2 px-3 py-1.5 text-left text-[13px] hover:bg-zinc-50",
        active && "bg-zinc-50",
      )}
    >
      <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", GAME_DOT[s.game])} />
      <span className={cn("flex-1 truncate", active ? "font-medium text-zinc-900" : "text-zinc-700")}>
        {s.label}
        {s.codename && <span className="ml-1.5 text-[11px] text-zinc-400">{s.codename}</span>}
      </span>
      {active && <Check className="h-3.5 w-3.5 text-zinc-900" />}
    </button>
  );
}

/** 顶部分析对象切换器：按游戏分组的版本选择（演示模式）。 */
export function StudySwitcher() {
  const [study, setStudy] = useState<StudyMeta>(STUDIES[0]);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const id = currentStudyId();
    const s = STUDIES.find((x) => x.id === id);
    if (s) setStudy(s);
  }, []);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const games: { key: "genshin" | "wuthering_waves"; name: string }[] = [
    { key: "genshin", name: "原神" },
    { key: "wuthering_waves", name: "鸣潮" },
  ];

  return (
    <div className="relative" ref={ref} data-study-switcher>
      <button
        onClick={() => setOpen(!open)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex h-8 items-center gap-2 rounded-md border border-zinc-200 bg-white px-2.5 text-[13px] hover:border-zinc-300"
      >
        <span className={cn("h-1.5 w-1.5 rounded-full", GAME_DOT[study.game])} />
        <span className="font-medium text-zinc-900">{study.label}</span>
        {study.codename && <span className="hidden text-[11px] text-zinc-400 sm:inline">{study.codename}</span>}
        <ChevronDown className="h-3.5 w-3.5 text-zinc-400" />
      </button>
      {open && (
        <div
          role="listbox"
          className="absolute right-0 z-50 mt-1 w-64 overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-lg"
        >
          {games.map((g) => (
            <div key={g.key}>
              <div className="border-b border-zinc-100 bg-zinc-50/60 px-3 py-1 text-[10px] font-medium uppercase tracking-wide text-zinc-400">
                {g.name}
              </div>
              {STUDIES.filter((s) => s.game === g.key).map((s) => (
                <StudyRow
                  key={s.id}
                  s={s}
                  active={s.id === study.id}
                  onPick={() => {
                    if (s.id !== study.id) {
                      setStudyId(s.id);
                      window.location.reload();
                    }
                    setOpen(false);
                  }}
                />
              ))}
            </div>
          ))}
          <div className="border-t border-zinc-100 px-3 py-1.5 text-[10px] leading-4 text-zinc-400">
            切换分析单元后页面按对应冻结样本重载
          </div>
        </div>
      )}
    </div>
  );
}
