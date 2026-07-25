import type { PaperStatus, PublicReport } from "@/lib/types";
import { localizeEvaluationValue } from "@/lib/evaluationLocalization";
import { buildStudentSummary, formatScore, getReportTitle, normalizePublicDimensions } from "@/lib/report";
import { Download, Eye } from "lucide-react";

import { DimensionOverview } from "./DimensionOverview";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";

type StudentSummaryProps = {
  report: PublicReport;
  status?: PaperStatus | null;
  onDownload?: () => void;
  downloading?: boolean;
};

export function StudentSummary({ report, status, onDownload, downloading = false }: StudentSummaryProps) {
  const summary = buildStudentSummary(report);
  const dimensions = normalizePublicDimensions(report);

  const handlePreview = () => {
    window.open(`/api/papers/${report.paper_id}/export/simple`, "_blank");
  };

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader className="pb-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-2">
              <Badge variant="default">给学生/投稿人的摘要</Badge>
              <CardTitle className="text-xl">{getReportTitle(report)}</CardTitle>
              <CardDescription>面向作者修改的公开视图，不展示真实模型名和内部复核细节。</CardDescription>
            </div>
            <div className="flex shrink-0 flex-col gap-3 rounded-2xl border border-blue-100 bg-blue-50 px-5 py-4 text-center">
              <div className="text-xs font-medium text-blue-600">综合参考分</div>
              <div className="text-3xl font-semibold text-blue-700">{formatScore(report.weighted_total)}</div>
              <div className="flex gap-2">
                <Button type="button" variant="outline" size="sm" onClick={handlePreview} className="bg-white">
                  <Eye className="h-4 w-4" />
                  预览
                </Button>
                {onDownload ? (
                  <Button type="button" variant="outline" size="sm" onClick={onDownload} disabled={downloading} className="bg-white">
                    <Download className="h-4 w-4" />
                    {downloading ? "下载中" : "下载"}
                  </Button>
                ) : null}
              </div>
            </div>
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
          <section className="rounded-xl border border-slate-200 bg-white p-4">
            <h3 className="text-sm font-semibold text-slate-950">整体判断</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">{summary.overall}</p>
          </section>
          <section className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <h3 className="text-sm font-semibold text-slate-950">流程状态</h3>
            <div className="mt-3 flex flex-wrap gap-2">
              <Badge variant="neutral">
                论文：{localizeEvaluationValue(status?.paper_status)}
              </Badge>
              <Badge variant="neutral">
                任务：{localizeEvaluationValue(status?.task_status)}
              </Badge>
              <Badge variant={status?.precheck_status === "passed" ? "success" : "warning"}>
                预检：{localizeEvaluationValue(status?.precheck_status)}
              </Badge>
            </div>
          </section>
        </CardContent>
      </Card>

      {status?.progress && status.progress.percent < 100 ? (
        <Card>
          <CardHeader>
            <CardTitle>评价进度</CardTitle>
            <CardDescription>
              {status.progress.stage_label}
              {status.progress.current_dimension
                ? ` · ${dimensionLabel(status.progress.current_dimension)}`
                : ""}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div
              className="h-2 overflow-hidden rounded-full bg-slate-100"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={status.progress.percent}
            >
              <div
                className="h-full rounded-full bg-blue-600 transition-all"
                style={{ width: `${status.progress.percent}%` }}
              />
            </div>
            <div className="mt-2 flex justify-between text-xs text-slate-500">
              <span>
                已完成 {status.progress.completed}/{status.progress.total} 个处理单元
              </span>
              <span>{status.progress.percent}%</span>
            </div>
            {status.progress.is_stalled ? (
              <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700">
                处理进度长时间未更新，系统正在等待恢复；如持续不变请联系管理员。
              </p>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      <DimensionOverview dimensions={dimensions} mode="student" />

      <div className="grid gap-4 lg:grid-cols-3">
        <InsightCard title="主要优势" items={summary.strengths} />
        <InsightCard title="优先修改" items={summary.priorities} />
        <Card>
          <CardHeader>
            <CardTitle>专家/编辑意见</CardTitle>
            <CardDescription>如与模型摘要存在差异，以专家/编辑意见为准。</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-6 text-slate-600">{summary.expertText}</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function dimensionLabel(key: string): string {
  const labels: Record<string, string> = {
    problem_originality: "研究创新性",
    literature_insight: "现状洞察度",
    analytical_framework: "理论建构力",
    logical_coherence: "逻辑连贯性",
    conclusion_consensus: "学术共识度",
    forward_extension: "前瞻延展性",
  };
  return labels[key] ?? key;
}

function InsightCard({ title, items }: { title: string; items: string[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="space-y-3 text-sm leading-6 text-slate-600">
          {(items.length > 0 ? items : ["暂无足够数据生成摘要。"] ).map((item) => (
            <li key={item} className="rounded-xl border border-slate-200 bg-white p-3">
              {item}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
