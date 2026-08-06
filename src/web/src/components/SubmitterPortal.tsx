import { FormEvent, useEffect, useState } from "react";
import { FileText, UploadCloud } from "lucide-react";

import {
  exportSimpleReport,
  getPaperStatus,
  getPublicReport,
  listSubmitterJournals,
  listSubmitterSubmissions,
  requestSubmissionWithdrawal,
  uploadSubmitterSubmission,
} from "@/lib/api";
import type {
  PaperStatus,
  PublicReport,
  SubmitterJournal,
  SubmitterSubmission,
} from "@/lib/types";
import { cn } from "@/lib/utils";

import { StudentSummary } from "./StudentSummary";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Input } from "./ui/input";
import { Select } from "./ui/select";

const statusLabel: Record<string, string> = {
  pending: "待处理",
  prechecking: "准入检查中",
  precheck_failed: "准入未通过",
  evaluating: "评价中",
  reviewing: "专家复核中",
  completed: "已完成",
  failed: "处理失败",
  recovering: "恢复中",
};

export function SubmitterPortal() {
  const [journals, setJournals] = useState<SubmitterJournal[]>([]);
  const [submissions, setSubmissions] = useState<SubmitterSubmission[]>([]);
  const [selectedSubmissionId, setSelectedSubmissionId] = useState<string | null>(null);
  const [status, setStatus] = useState<PaperStatus | null>(null);
  const [report, setReport] = useState<PublicReport | null>(null);
  const [message, setMessage] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [withdrawing, setWithdrawing] = useState(false);

  const refreshSubmissions = async () =>
    setSubmissions(await listSubmitterSubmissions());
  const selectedSubmission = submissions.find(
    (item) => item.id === selectedSubmissionId
  );

  useEffect(() => {
    void Promise.all([listSubmitterJournals(), listSubmitterSubmissions()])
      .then(([journalRows, submissionRows]) => {
        setJournals(journalRows);
        setSubmissions(submissionRows);
      })
      .catch(() => {
        setJournals([]);
        setSubmissions([]);
      });
  }, []);

  useEffect(() => {
    if (submissions.length > 0 && !selectedSubmissionId) {
      setSelectedSubmissionId(submissions[0].id);
    }
  }, [submissions, selectedSubmissionId]);

  useEffect(() => {
    if (!selectedSubmission) return;
    let isCurrent = true;
    const paperId = selectedSubmission.paper_id;
    const refresh = async () => {
      const nextStatus = await getPaperStatus(paperId);
      if (!isCurrent) return;
      setStatus(nextStatus);
      if (selectedSubmission.report_released) {
        const nextReport = await getPublicReport(paperId);
        if (!isCurrent) return;
        const reportPaperId = nextReport.paper_id;
        if (reportPaperId && reportPaperId !== paperId) return;
        setReport(nextReport);
      }
    };
    void refresh().catch(() => {
      if (!isCurrent) return;
      setStatus(null);
      setReport(null);
    });
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void refresh().catch(() => undefined);
      }
    }, 3000);
    return () => {
      window.clearInterval(timer);
      isCurrent = false;
    };
  }, [selectedSubmission?.id, selectedSubmission?.report_released]);

  const handleUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const input = form.elements.namedItem("paper") as HTMLInputElement | null;
    const title = (form.elements.namedItem("title") as HTMLInputElement | null)?.value;
    const unitId = (form.elements.namedItem("unit_id") as HTMLSelectElement | null)?.value;
    const file = input?.files?.[0];
    if (!file || !title || !unitId) return;
    try {
      const payload = await uploadSubmitterSubmission(unitId, title, file);
      setMessage(`投稿成功，系统稿号：${payload.submission_id}；预审完成后意见将由编辑发布。`);
      setSelectedSubmissionId(payload.submission_id);
      await refreshSubmissions();
      form.reset();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "投稿失败");
    }
  };

  const handleDownloadReport = async () => {
    if (!selectedSubmission) return;
    setDownloading(true);
    try {
      const blob = await exportSimpleReport(selectedSubmission.paper_id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `report-${selectedSubmission.id}.pdf`;
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

  const handleWithdrawal = async () => {
    if (!selectedSubmission) return;
    const reason = window.prompt(
      "请填写撤稿原因（至少 5 个字符）。撤稿需要编辑确认，系统会保留稿号和审计记录。"
    );
    if (!reason) return;
    setWithdrawing(true);
    try {
      await requestSubmissionWithdrawal(selectedSubmission.id, reason);
      setMessage("撤稿申请已提交，等待编辑处理。");
      await refreshSubmissions();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "撤稿申请提交失败");
    } finally {
      setWithdrawing(false);
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
                <CardTitle>投稿人入口</CardTitle>
                <CardDescription>选择正式启用的期刊提交稿件，获取智能辅助预审意见以改进论文质量。</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleUpload} className="space-y-3">
              <Select name="unit_id" required disabled={journals.length === 0}>
                <option value="">选择投稿期刊</option>
                {journals.map((journal) => (
                  <option key={journal.unit_id} value={journal.unit_id}>
                    {journal.journal_name} · {journal.unit_name}
                  </option>
                ))}
              </Select>
              <Input name="title" placeholder="论文题目" required minLength={2} />
              <Input name="paper" type="file" accept=".pdf,.docx,.txt" />
              <p className="text-xs leading-5 text-slate-500">
                支持 PDF、DOCX、TXT。扫描版 PDF 默认不做 OCR，请上传可解析文本版本。
              </p>
              <Button type="submit" className="w-full" disabled={journals.length === 0}>
                提交稿件
              </Button>
            </form>
            {journals.length === 0 ? (
              <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700">
                当前没有正式开放投稿的期刊，请稍后再试。
              </p>
            ) : null}
            {message ? <p className="mt-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{message}</p> : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>我的投稿</CardTitle>
            <CardDescription>查看处理进度、已发布结果或提交撤稿申请。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {submissions.length === 0 ? (
                <EmptyHint text="暂无投稿，请先选择期刊提交稿件。" />
              ) : (
                submissions.map((submission) => (
                  <div
                    key={submission.id}
                    className={cn(
                      "group rounded-xl border p-3 transition-colors",
                      submission.id === selectedSubmissionId
                        ? "border-blue-200 bg-blue-50"
                        : "border-slate-200 bg-white hover:bg-slate-50"
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedSubmissionId(submission.id);
                          setReport(null);
                        }}
                        className="min-w-0 flex-1 text-left"
                      >
                        <p className="truncate text-sm font-medium text-slate-950">{submission.title}</p>
                        <p className="mt-1 text-xs text-slate-500">
                          {submission.journal_name} · {submission.id}
                        </p>
                      </button>
                      <div className="flex items-center gap-2">
                        <Badge variant={submission.report_released ? "success" : "warning"}>
                          {submission.withdrawal_status === "pending"
                            ? "撤稿处理中"
                            : submission.status_label}
                        </Badge>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      </aside>

      <main className="space-y-5">
        {selectedSubmission?.report_released ? (
          <>
            <Card>
              <CardHeader>
                <div className="flex items-center gap-3">
                  <FileText className="h-5 w-5 text-blue-700" />
                  <div>
                    <CardTitle>编辑发布结果</CardTitle>
                    <CardDescription>{selectedSubmission.status_label}</CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm leading-7 text-slate-700">
                  {selectedSubmission.author_message}
                </p>
              </CardContent>
            </Card>
            {report ? (
              <StudentSummary report={report} status={status} onDownload={handleDownloadReport} downloading={downloading} />
            ) : (
              <EmptyHint text="公开报告正在加载。" />
            )}
          </>
        ) : status ? (
          <>
            <ProgressOnly status={status} />
            {selectedSubmission && selectedSubmission.status !== "withdrawn" ? (
              <Button
                type="button"
                variant="outline"
                onClick={handleWithdrawal}
                disabled={
                  withdrawing || selectedSubmission.withdrawal_status === "pending"
                }
              >
                {selectedSubmission.withdrawal_status === "pending"
                  ? "撤稿申请处理中"
                  : "申请撤稿"}
              </Button>
            ) : null}
          </>
        ) : (
          <Card>
            <CardContent className="p-10">
              <EmptyHint text="选择一篇论文查看预审结果。" />
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}

function ProgressOnly({ status }: { status: PaperStatus }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>论文预审中</CardTitle>
        <CardDescription>{status.progress.stage_label}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-2 overflow-hidden rounded-full bg-slate-100">
          <div
            className="h-full rounded-full bg-blue-600 transition-all"
            style={{ width: `${status.progress.percent}%` }}
          />
        </div>
        <p className="mt-3 text-sm text-slate-600">
          已完成 {status.progress.completed}/{status.progress.total} 个处理单元，
          当前进度 {status.progress.percent}%。
        </p>
        {status.progress.is_stalled ? (
          <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700">
            处理进度长时间未更新，系统正在等待恢复。
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

function EmptyHint({ text }: { text: string }) {
  return <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">{text}</div>;
}
