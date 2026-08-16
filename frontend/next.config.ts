import type { NextConfig } from "next";

const isDemo = process.env.NEXT_PUBLIC_DEMO === "1";
// GitHub Pages 项目页路径（部署时按仓库名设置，如 /liveops-community-intelligence）
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

const nextConfig: NextConfig = {
  ...(isDemo ? { output: "export" as const, images: { unoptimized: true } } : {}),
  ...(basePath && isDemo ? { basePath, trailingSlash: true } : {}),
};

export default nextConfig;
