import type { DimensionMetric } from "@/lib/types";
import { formatScore } from "@/lib/report";
import { cn } from "@/lib/utils";

import { Badge } from "./ui/badge";

type DimensionBreakdownListProps = {
  dimensions: DimensionMetric[];
  mode?: "student" | "internal";
};

export function DimensionBreakdownList({ dimensions, mode = "student" }: DimensionBreakdownListProps) {
  return (
    <div data-testid="dimension-breakdown-list" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {dimensions.map((dimension) => (
        <article key={dimension.key} className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h4 className="text-sm font-semibold text-slate-950">{dimension.name}</h4>
              {dimension.nameEn ? <p className="mt-0.5 text-xs text-slate-500">{dimension.nameEn}</p> : null}
            </div>
            <div className="text-right">
              <div className="text-lg font-semibold text-blue-700">{formatScore(dimension.score)}</div>
              <div className="text-[11px] text-slate-400">/ 100</div>
            </div>
          </div>
          {mode === "internal" ? (
            <div className="mt-3 flex flex-wrap gap-2">
              <Badge variant={dimension.confidence === "高置信度" ? "success" : "warning"}>{dimension.confidence}</Badge>
              {typeof dimension.stdScore === "number" ? <Badge variant="neutral">std {formatScore(dimension.stdScore)}</Badge> : null}
              {typeof dimension.weight === "number" ? <Badge variant="neutral">权重 {(dimension.weight * 100).toFixed(0)}%</Badge> : null}
            </div>
          ) : null}
          <p className={cn("mt-3 text-sm leading-6 text-slate-600", !dimension.summary && "text-slate-400")}>
            {dimension.summary || "暂无分项摘要。"}
          </p>
        </article>
      ))}
    </div>
  );
}
