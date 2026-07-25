import { Send } from "lucide-react";
import type { ExpertDecisionState, InternalDimensionScore, InternalReport } from "@/lib/types";
import {
  buildReviewOpinions,
  formatScore,
  getReportTitle,
  normalizeInternalDimension,
  normalizeInternalDimensions,
} from "@/lib/report";
import { cn } from "@/lib/utils";

import { DimensionOverview } from "./DimensionOverview";
import { ModelComparisonTable } from "./ModelComparisonTable";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Separator } from "./ui/separator";

type InternalReportViewProps = {
  report: InternalReport;
  decisions: Record<string, ExpertDecisionState>;
  onDecisionChange?: (opinionId: string, decision: ExpertDecisionState) => void;
  onSubmit?: () => void;
  readonly?: boolean;
};

export function InternalReportView({ report, decisions, onDecisionChange, onSubmit, readonly = false }: InternalReportViewProps) {
  const dimensions = normalizeInternalDimensions(report);
  const lowConfidence = dimensions.filter((dimension) => dimension.confidence !== "高置信度");

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-2">
              <Badge variant="violet">内部评价表</Badge>
              <CardTitle className="text-xl">{getReportTitle(report)}</CardTitle>
              <CardDescription>
                任务编号：{report.task_id ?? "未知"} · 论文编号：{report.paper_id ?? "未知"}
              </CardDescription>
            </div>
            <div className="grid w-full grid-cols-3 gap-2 text-center lg:w-auto lg:min-w-[360px]">
              <Metric label="六维综合参考分" value={formatScore(report.weighted_total)} />
              <Metric label="预检" value={localizedStatus(report.precheck_status)} />
              <Metric label="低置信维度" value={`${lowConfidence.length}`} />
            </div>
          </div>
        </CardHeader>
      </Card>

      <DimensionOverview dimensions={dimensions} mode="internal" title="内部六维指标" />

      <PrecheckCard result={report.precheck_result} status={report.precheck_status} />

      <div className="space-y-5">
        {report.dimensions?.map((dimension, index) => (
          <InternalDimensionCard
            key={dimension.key ?? index}
            dimension={dimension}
            index={index}
            decisions={decisions}
            onDecisionChange={onDecisionChange}
            readonly={readonly}
          />
        ))}
      </div>

      {!readonly && onSubmit && (
        <div className="sticky bottom-4 z-10 mx-auto mt-4 max-w-md">
          <Button type="button" className="w-full shadow-lg" onClick={onSubmit}>
            <Send className="h-4 w-4" />
            提交复核意见
          </Button>
        </div>
      )}
    </div>
  );
}

function InternalDimensionCard({
  dimension,
  index,
  decisions,
  onDecisionChange,
  readonly,
}: {
  dimension: InternalDimensionScore;
  index: number;
  decisions: Record<string, ExpertDecisionState>;
  onDecisionChange?: (opinionId: string, decision: ExpertDecisionState) => void;
  readonly: boolean;
}) {
  const metric = normalizeInternalDimension(dimension, index);
  const opinions = buildReviewOpinions(dimension, index);

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <CardTitle>{metric.name}</CardTitle>
            <CardDescription>学术质量评价维度</CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="default">均分 {formatScore(metric.score)}</Badge>
            {typeof metric.stdScore === "number" ? <Badge variant="neutral">标准差 {formatScore(metric.stdScore)}</Badge> : null}
            <Badge variant={metric.confidence === "高置信度" ? "success" : "warning"}>{metric.confidence}</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <section>
          <h4 className="mb-2 text-sm font-semibold text-slate-950">匿名模型对照</h4>
          <ModelComparisonTable dimension={dimension} />
        </section>
        <Separator />
        <section className="space-y-6">
          <div>
            <h4 className="text-sm font-semibold text-slate-950">智能辅助证据与判断</h4>
            <p className="mt-1 text-sm text-slate-500">每条意见为独立视觉块，三态按钮位于正文正下方居中。</p>
          </div>
          {opinions.map((opinion) => (
            <article key={opinion.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="space-y-3">
                <div>
                  <h5 className="text-sm font-semibold text-slate-950">{opinion.title}</h5>
                  <p className="mt-2 text-sm leading-6 text-slate-600">{opinion.body}</p>
                </div>
                {opinion.evidence ? (
                  <blockquote className="rounded-xl border-l-4 border-blue-200 bg-white px-4 py-3 text-sm leading-6 text-slate-600">
                    {opinion.evidence}
                  </blockquote>
                ) : null}
              </div>
              <div className="mt-4 flex justify-center pt-2">
                <ExpertDecisionControls
                  value={decisions[opinion.id] ?? "neutral"}
                  onChange={(decision) => onDecisionChange?.(opinion.id, decision)}
                  disabled={readonly}
                />
              </div>
            </article>
          ))}
        </section>
      </CardContent>
    </Card>
  );
}

function ExpertDecisionControls({
  value,
  onChange,
  disabled,
}: {
  value: ExpertDecisionState;
  onChange: (value: ExpertDecisionState) => void;
  disabled?: boolean;
}) {
  const options: Array<{ value: ExpertDecisionState; label: string; title: string }> = [
    { value: "accept", label: "✓", title: "认可" },
    { value: "reject", label: "×", title: "不认可" },
    { value: "neutral", label: "−", title: "无意见" },
  ];

  return (
    <div className="inline-flex rounded-xl border border-slate-200 bg-white p-1" aria-label="专家三态确认">
      {options.map((option) => (
        <Button
          key={option.value}
          type="button"
          size="sm"
          variant="ghost"
          disabled={disabled}
          title={option.title}
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            "h-8 min-w-10 rounded-lg px-3 text-base",
            value === option.value && option.value === "accept" && "bg-emerald-50 text-emerald-700 hover:bg-emerald-50",
            value === option.value && option.value === "reject" && "bg-red-50 text-red-700 hover:bg-red-50",
            value === option.value && option.value === "neutral" && "bg-slate-100 text-slate-700 hover:bg-slate-100"
          )}
        >
          {option.label}
        </Button>
      ))}
    </div>
  );
}

function PrecheckCard({ status, result }: { status?: string | null; result?: InternalReport["precheck_result"] }) {
  const entries = typeof result === "object" && result !== null ? Object.entries(result) : [];
  return (
    <Card>
      <CardHeader>
        <CardTitle>预检结果</CardTitle>
        <CardDescription>写作规范性、引用规范性与学术伦理检查的可读摘要。</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="mb-3">
          <Badge variant={status === "passed" ? "success" : "warning"}>{localizedStatus(status)}</Badge>
        </div>
        {typeof result === "string" ? <p className="text-sm leading-6 text-slate-600">{result}</p> : null}
        {entries.length > 0 ? (
          <dl className="grid gap-3 md:grid-cols-3">
            {entries.map(([key, value]) => (
              <div key={key} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <dt className="text-xs font-medium text-slate-500">{precheckFieldLabel(key)}</dt>
                <dd className="mt-2 text-sm leading-6 text-slate-700">{localizedStatus(String(value))}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        {!result ? <p className="text-sm text-slate-500">暂无预检详情。</p> : null}
      </CardContent>
    </Card>
  );
}

function precheckFieldLabel(key: string): string {
  return (
    {
      status: "状态",
      conclusion: "结论",
      boundary_status: "边界判断",
      boundary_reasons: "边界理由",
      reasons: "理由",
      evidence_quotes: "原文证据",
      confidence: "可信程度",
    }[key] ?? "补充信息"
  );
}

function localizedStatus(value?: string | null): string {
  const text = String(value ?? "");
  return (
    {
      passed: "通过",
      pass: "通过",
      boundary: "边界，需确认",
      boundary_review: "边界复核",
      reject: "不通过",
      pending: "待处理",
      high: "高",
      medium: "中等",
      low: "较低",
      critical: "很低",
      true: "是",
      false: "否",
    }[text] ?? (text || "待确认")
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-slate-200 bg-slate-50 px-3 py-3">
      <div className="whitespace-nowrap text-[11px] text-slate-500">{label}</div>
      <div className="mt-1 truncate text-sm font-semibold text-slate-950" title={value}>{value}</div>
    </div>
  );
}
