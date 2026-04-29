import type { PaperStatus, PublicReport } from "@/lib/types";
import { buildStudentSummary, formatScore, getReportTitle, normalizePublicDimensions } from "@/lib/report";
import { Download } from "lucide-react";

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
              <div className="text-xs font-medium text-blue-600">综合总分</div>
              <div className="text-3xl font-semibold text-blue-700">{formatScore(report.weighted_total)}</div>
              {onDownload ? (
                <Button type="button" variant="outline" size="sm" onClick={onDownload} disabled={downloading} className="bg-white">
                  <Download className="h-4 w-4" />
                  {downloading ? "下载中" : "下载 PDF"}
                </Button>
              ) : null}
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
              <Badge variant="neutral">论文：{status?.paper_status ?? "未知"}</Badge>
              <Badge variant="neutral">任务：{status?.task_status ?? "未知"}</Badge>
              <Badge variant={status?.precheck_status === "passed" ? "success" : "warning"}>
                预检：{status?.precheck_status ?? "待确认"}
              </Badge>
            </div>
          </section>
        </CardContent>
      </Card>

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
