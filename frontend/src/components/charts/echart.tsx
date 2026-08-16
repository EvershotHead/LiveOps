"use client";

import { useEffect, useRef } from "react";
import * as echarts from "echarts";

export type EChartOption = echarts.EChartsOption;

/** ECharts 统一封装：紧凑运营主题，空数据不渲染图。 */
export function EChart({ option, height = 260, dataCount }: {
  option: EChartOption;
  height?: number;
  dataCount?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    if (!chartRef.current) {
      chartRef.current = echarts.init(ref.current);
    }
    const c = chartRef.current;
    c.setOption({
      textStyle: { fontFamily: "inherit", fontSize: 11, color: "#52525b" },
      grid: { left: 8, right: 12, top: 24, bottom: 4, containLabel: true },
      tooltip: { trigger: "axis", textStyle: { fontSize: 11 } },
      ...option,
    });
    const onResize = () => c.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      c.dispose();
      chartRef.current = null;
    };
  }, [option]);

  if (dataCount === 0) {
    return (
      <div className="flex items-center justify-center text-xs text-zinc-400" style={{ height }}>
        无数据
      </div>
    );
  }
  return <div ref={ref} style={{ height, width: "100%" }} role="img" aria-label="图表" />;
}
