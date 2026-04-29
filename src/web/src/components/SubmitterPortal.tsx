import { FormEvent, useEffect, useState } from "react";
import { UploadCloud } from "lucide-react";

import { exportSimpleReport, getPaperStatus, getPublicReport, listPapers, uploadPaper } from "@/lib/api";
import type { PaperListItem, PaperStatus, PublicReport } from "@/lib/types";
import { cn } from "@/lib/utils";

import { StudentSummary } from "./StudentSummary";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Input } from "./ui/input";

const statusLabel: Record<string, string> = {
  pending: "待处理",
  prechecking: "准入检查中",
  precheck_failed: "准入未通过",
  evaluating: "评价中",
  reviewing: "专家复核中",
  completed: "已完成",
  failed: "处理失败",
};

export function SubmitterPortal() {
  const [papers, setPapers] = useState<PaperListItem[]>([]);
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null);
  const [status, setStatus] = useState<PaperStatus | null>(null);
  const [report, setReport] = useState<PublicReport | null>(null);
  const [message, setMessage] = useState("");
  const [downloading, setDownloading] = useState(false);

  const refreshPapers = async () => setPapers(await listPapers());

  useEffect(() => {
    void refreshPapers().catch(() => setPapers([]));
  }, []);

  useEffect(() => {
    if (papers.length > 0 && !selectedPaperId) setSelectedPaperId(papers[0].paper_id);
  }, [papers, selectedPaperId]);

  useEffect(() => {
    if (!selectedPaperId) return;
    let isCurrent = true;
    const paperId = selectedPaperId;
    void Promise.all([getPaperStatus(selectedPaperId), getPublicReport(selectedPaperId)])
      .then(([nextStatus, nextReport]) => {
        if (!isCurrent) return;
        const reportPaperId = nextReport.paper_id;
        if (reportPaperId && reportPaperId !== paperId) return;
        setStatus(nextStatus);
        setReport(nextReport);
      })
      .catch(() => {
        if (!isCurrent) return;
        setStatus(null);
        setReport(null);
      });
    return () => {
      isCurrent = false;
    };
  }, [selectedPaperId]);

  const handleUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const input = event.currentTarget.elements.namedItem("paper") as HTMLInputElement | null;
    const file = input?.files?.[0];
    if (!file) return;
    const payload = await uploadPaper(file);
    setMessage(`上传成功：${payload.paper_id}`);
    setSelectedPaperId(payload.paper_id);
    await refreshPapers();
    event.currentTarget.reset();
  };

  const handleDownloadReport = async () => {
    if (!selectedPaperId) return;
    setDownloading(true);
    try {
      const blob = await exportSimpleReport(selectedPaperId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `report-${selectedPaperId}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "下载失败");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="grid gap-5 xl:grid-cols-[360px_1fr]">
      <aside className="space-y-5 xl:sticky xl:top-24 xl:max-h-[calc(100vh-7rem)] xl:overflow-y-auto xl:pr-1">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="rounded-xl border border-blue-100 bg-blue-50 p-2 text-blue-700">
                <UploadCloud className="h-5 w-5" />
              </div>
              <div>
                <CardTitle>学生/投稿人入口</CardTitle>
                <CardDescription>上传论文、查看进度、下载公开报告。</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleUpload} className="space-y-3">
              <Input name="paper" type="file" accept=".pdf,.docx,.txt" />
              <p className="text-xs leading-5 text-slate-500">
                支持 PDF、DOCX、TXT。扫描版 PDF 默认不做 OCR，请上传可解析文本版本。
              </p>
              <Button type="submit" className="w-full">上传论文</Button>
            </form>
            {message ? <p className="mt-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{message}</p> : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>我的论文</CardTitle>
            <CardDescription>选择一篇论文查看公开评价摘要。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {papers.length === 0 ? (
                <EmptyHint text="暂无论文，请先上传。" />
              ) : (
                papers.map((paper) => (
                  <button
                    key={paper.paper_id}
                    type="button"
                    onClick={() => setSelectedPaperId(paper.paper_id)}
                    className={cn(
                      "w-full rounded-xl border p-3 text-left transition-colors",
                      paper.paper_id === selectedPaperId
                        ? "border-blue-200 bg-blue-50"
                        : "border-slate-200 bg-white hover:bg-slate-50"
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-slate-950">{paper.title ?? paper.original_filename}</p>
                        <p className="mt-1 text-xs text-slate-500">{paper.original_filename}</p>
                      </div>
                      <StatusBadge status={paper.paper_status} />
                    </div>
                  </button>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      </aside>

      <main className="space-y-5">
        {report ? (
          <StudentSummary report={report} status={status} onDownload={handleDownloadReport} downloading={downloading} />
        ) : (
          <Card>
            <CardContent className="p-10">
              <EmptyHint text="选择一篇论文查看评价结果。" />
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const variant = status === "completed" ? "success" : status === "failed" || status === "precheck_failed" ? "danger" : "warning";
  return <Badge variant={variant} className="shrink-0 whitespace-nowrap px-2 py-0 text-[11px] leading-5">{statusLabel[status] ?? status}</Badge>;
}

function EmptyHint({ text }: { text: string }) {
  return <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">{text}</div>;
}
