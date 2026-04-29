import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { RadarChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { SVGRenderer } from "echarts/renderers";

import type { DimensionMetric } from "@/lib/types";

echarts.use([RadarChart, TooltipComponent, GridComponent, SVGRenderer]);

type DimensionRadarChartProps = {
  dimensions: DimensionMetric[];
  compact?: boolean;
};

export function DimensionRadarChart({ dimensions, compact = false }: DimensionRadarChartProps) {
  const chartRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const element = chartRef.current;
    if (!element || dimensions.length === 0) return;

    const chart = echarts.init(element, undefined, { renderer: "svg" });
    chart.setOption({
      color: ["#2563eb"],
      tooltip: { trigger: "item" },
      radar: {
        radius: compact ? "62%" : "70%",
        center: ["50%", "52%"],
        splitNumber: 4,
        indicator: dimensions.map((dimension) => ({ name: dimension.name, max: 100 })),
        axisName: {
          color: "#475569",
          fontSize: compact ? 11 : 12,
        },
        splitLine: { lineStyle: { color: "#e2e8f0" } },
        splitArea: { areaStyle: { color: ["#ffffff", "#f8fafc"] } },
        axisLine: { lineStyle: { color: "#e2e8f0" } },
      },
      series: [
        {
          name: "六维指标",
          type: "radar",
          symbol: "circle",
          symbolSize: 4,
          lineStyle: { width: 2, color: "#2563eb" },
          areaStyle: { color: "rgba(37, 99, 235, 0.16)" },
          data: [{ value: dimensions.map((dimension) => dimension.score), name: "当前评价" }],
        },
      ],
    });

    const resize = () => chart.resize();
    let observer: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(resize);
      observer.observe(element);
    } else {
      window.addEventListener("resize", resize);
    }

    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, [compact, dimensions]);

  return (
    <div
      ref={chartRef}
      data-testid="dimension-radar-chart"
      className={compact ? "h-72 w-full" : "h-80 w-full md:h-88"}
      aria-label="六维指标雷达图"
    />
  );
}
