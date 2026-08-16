import type { Metadata } from "next";
import "./globals.css";
import { Shell } from "@/components/layout/shell";

export const metadata: Metadata = {
  title: "LiveOps Community Intelligence",
  description: "游戏版本社区洞察与运营复盘系统 · 所采样的 B 站讨论口径",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const mode = process.env.NEXT_PUBLIC_DEMO === "1" ? "demo" : "local";
  return (
    <html lang="zh-CN">
      <body className="antialiased">
        <Shell mode={mode as "local" | "demo"}>{children}</Shell>
      </body>
    </html>
  );
}
