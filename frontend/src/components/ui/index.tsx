"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

/* 手写 shadcn 风格基础组件（紧凑运营工作台视觉，无渐变无卡片套卡片）。 */

export function Button({ className, variant = "default", size = "md", ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "outline" | "ghost" | "destructive";
  size?: "sm" | "md";
}) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-1 rounded-md font-medium transition-colors disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-1",
        size === "sm" ? "h-7 px-2.5 text-xs" : "h-8 px-3 text-sm",
        variant === "default" && "bg-zinc-900 text-zinc-50 hover:bg-zinc-700",
        variant === "outline" && "border border-zinc-300 bg-white hover:bg-zinc-50 text-zinc-900",
        variant === "ghost" && "hover:bg-zinc-100 text-zinc-700",
        variant === "destructive" && "bg-red-600 text-white hover:bg-red-500",
        className,
      )}
      {...props}
    />
  );
}

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-lg border border-zinc-200 bg-white", className)} {...props} />;
}

export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-0.5 border-b border-zinc-100 px-4 py-2.5", className)} {...props} />;
}

export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-sm font-semibold text-zinc-900", className)} {...props} />;
}

export function CardDesc({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-xs text-zinc-500", className)} {...props} />;
}

export function CardBody({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-4", className)} {...props} />;
}

export function Badge({ className, tone = "default", ...props }: React.HTMLAttributes<HTMLSpanElement> & {
  tone?: "default" | "green" | "red" | "amber" | "blue" | "gray";
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-0.5 text-[11px] font-medium leading-4",
        tone === "default" && "border-zinc-200 bg-zinc-50 text-zinc-700",
        tone === "green" && "border-emerald-200 bg-emerald-50 text-emerald-700",
        tone === "red" && "border-red-200 bg-red-50 text-red-700",
        tone === "amber" && "border-amber-200 bg-amber-50 text-amber-700",
        tone === "blue" && "border-blue-200 bg-blue-50 text-blue-700",
        tone === "gray" && "border-zinc-200 bg-white text-zinc-500",
      )}
      {...props}
    />
  );
}

export function Table({ className, ...props }: React.TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className="w-full overflow-x-auto">
      <table className={cn("w-full border-collapse text-xs", className)} {...props} />
    </div>
  );
}

export function Th({ className, ...props }: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn("border-b border-zinc-200 bg-zinc-50 px-2.5 py-1.5 text-left font-medium text-zinc-600 whitespace-nowrap", className)}
      {...props}
    />
  );
}

export function Td({ className, ...props }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("border-b border-zinc-100 px-2.5 py-1.5 text-zinc-800 whitespace-nowrap", className)} {...props} />;
}

export function Tabs({ tabs, value, onChange }: {
  tabs: { key: string; label: string }[];
  value: string;
  onChange: (k: string) => void;
}) {
  return (
    <div className="flex border-b border-zinc-200" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.key}
          role="tab"
          aria-selected={value === t.key}
          onClick={() => onChange(t.key)}
          className={cn(
            "-mb-px border-b-2 px-3 py-1.5 text-xs font-medium",
            value === t.key ? "border-zinc-900 text-zinc-900" : "border-transparent text-zinc-500 hover:text-zinc-800",
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn("h-8 w-full rounded-md border border-zinc-300 px-2.5 text-sm focus:outline-2 focus:outline-zinc-400", className)}
      {...props}
    />
  );
}

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("text-xs font-medium text-zinc-700", className)} {...props} />;
}

export function Progress({ value, className }: { value: number; className?: string }) {
  return (
    <div className={cn("h-1.5 w-full overflow-hidden rounded bg-zinc-100", className)}>
      <div className="h-full bg-zinc-800" style={{ width: `${Math.min(100, Math.max(0, value * 100))}%` }} />
    </div>
  );
}

export function Separator({ className }: { className?: string }) {
  return <div className={cn("h-px w-full bg-zinc-200", className)} />;
}

export function ScopeNote({ text }: { text: string }) {
  return (
    <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-1.5 text-[11px] leading-5 text-amber-800">
      {text}
    </div>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="flex h-40 items-center justify-center text-xs text-zinc-400">{children}</div>;
}
