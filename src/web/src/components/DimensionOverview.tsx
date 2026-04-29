import type { DimensionMetric } from "@/lib/types";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { DimensionBreakdownList } from "./DimensionBreakdownList";
import { DimensionRadarChart } from "./DimensionRadarChart";

type DimensionOverviewProps = {
  title?: string;
  description?: string;
  dimensions: DimensionMetric[];
  mode?: "student" | "internal";
};

export function DimensionOverview({
  title = "六维指标概览",
  description = "雷达图用于快速定位优势与短板，下方分项用于逐项细读。",
  dimensions,
  mode = "student",
}: DimensionOverviewProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {dimensions.length > 0 ? (
          <>
            <DimensionRadarChart dimensions={dimensions} compact={mode === "student"} />
            <DimensionBreakdownList dimensions={dimensions} mode={mode} />
          </>
        ) : (
          <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-8 text-center text-sm text-slate-500">
            暂无六维指标数据。
          </div>
        )}
      </CardContent>
    </Card>
  );
}
