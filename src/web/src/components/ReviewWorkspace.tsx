import { useEffect, useMemo, useState } from "react";
import { ClipboardCheck, LockKeyhole, Send } from "lucide-react";

import {
  getExpertManuscript,
  getInternalReport,
  listMyReviews,
  submitBlindReview,
  submitReview,
} from "@/lib/api";
import {
  buildReviewOpinions,
  clampScore,
  normalizeInternalDimensions,
} from "@/lib/report";
import type {
  AnonymousManuscript,
  ExpertComparisonInput,
  ExpertDecisionState,
  InternalReport,
  ReviewCommentInput,
  ReviewTask,
  User,
} from "@/lib/types";
import { cn } from "@/lib/utils";

import { AnonymousManuscriptReader } from "./AnonymousManuscriptReader";
import { InternalReportView } from "./InternalReportView";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Input } from "./ui/input";
import { Textarea } from "./ui/textarea";

type WorkspaceTask = {
  id: string;
  taskId: string;
  paperId?: string | null;
  reviewId: string;
  title: string;
  status: string;
  stage: "blind" | "comparison" | "completed";
  requiredDimensions: string[];
};

const dimensionNames: Record<string, string> = {
  problem_originality: "研究创新性",
  literature_insight: "现状洞察度",
  analytical_framework: "理论建构力",
  logical_coherence: "逻辑连贯性",
  conclusion_consensus: "学术共识度",
  forward_extension: "前瞻延展性",
};

const stageLabels = {
  blind: "独立评阅",
  comparison: "对照复核",
  completed: "已完成",
};

export function ReviewWorkspace({ user }: { user: User }) {
  const [tasks, setTasks] = useState<WorkspaceTask[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [report, setReport] = useState<InternalReport | null>(null);
  const [manuscript, setManuscript] =
    useState<AnonymousManuscript | null>(null);
  const [manuscriptLoading, setManuscriptLoading] = useState(false);
  const [manuscriptError, setManuscriptError] = useState("");
  const [activeView, setActiveView] = useState<"manuscript" | "report">(
    "manuscript"
  );
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState<"success" | "error" | "info">(
    "info"
  );
  const [decisions, setDecisions] = useState<
    Record<string, ExpertDecisionState>
  >({});
  const [scoreDrafts, setScoreDrafts] = useState<Record<string, number>>({});
  const [reasonDrafts, setReasonDrafts] = useState<Record<string, string>>({});

  const selectedTask = tasks.find((task) => task.id === selectedTaskId) ?? tasks[0];

  const refresh = async () => {
    const reviewItems = await listMyReviews();
    const nextTasks = reviewItems.map(mapReviewTaskToTask);
    setTasks(nextTasks);
    setSelectedTaskId((current) =>
      nextTasks.some((task) => task.id === current)
        ? current
        : nextTasks[0]?.id ?? null
    );
  };

  useEffect(() => {
    void refresh().catch(() => setTasks([]));
  }, []);

  useEffect(() => {
    if (!selectedTask?.reviewId) {
      setManuscript(null);
      setManuscriptError("");
      return;
    }
    let isCurrent = true;
    setManuscriptLoading(true);
    setManuscriptError("");
    void getExpertManuscript(selectedTask.reviewId)
      .then((nextManuscript) => {
        if (!isCurrent) return;
        setManuscript(nextManuscript);
      })
      .catch((error) => {
        if (!isCurrent) return;
        setManuscript(null);
        setManuscriptError(
          error instanceof Error ? error.message : "匿名稿加载失败"
        );
      })
      .finally(() => {
        if (isCurrent) setManuscriptLoading(false);
      });
    return () => {
      isCurrent = false;
    };
  }, [selectedTask?.reviewId]);

  useEffect(() => {
    setActiveView(selectedTask?.stage === "blind" ? "manuscript" : "report");
  }, [selectedTask?.id, selectedTask?.stage]);

  useEffect(() => {
    if (!selectedTask?.paperId) {
      setReport(null);
      return;
    }
    let isCurrent = true;
    void getInternalReport(selectedTask.paperId, selectedTask.taskId)
      .then((nextReport) => {
        if (!isCurrent) return;
        setReport(nextReport);
        setScoreDrafts({});
        setReasonDrafts({});
        setDecisions({});
      })
      .catch(() => {
        if (isCurrent) setReport(null);
      });
    return () => {
      isCurrent = false;
    };
  }, [
    selectedTask?.paperId,
    selectedTask?.taskId,
    selectedTask?.stage,
  ]);

  const allMetrics = useMemo(() => normalizeInternalDimensions(report), [report]);
  const metrics = useMemo(() => {
    if (!selectedTask?.requiredDimensions.length) return allMetrics;
    const required = new Set(selectedTask.requiredDimensions);
    return allMetrics.filter((metric) => required.has(metric.key));
  }, [allMetrics, selectedTask]);
  const opinionsByDimension = useMemo(() => {
    if (!report?.dimensions) return {};
    return Object.fromEntries(
      report.dimensions.map((dimension, index) => {
        const key =
          dimension.key ?? allMetrics[index]?.key ?? `dimension-${index + 1}`;
        return [key, buildReviewOpinions(dimension, index)];
      })
    );
  }, [allMetrics, report]);

  const handleBlindSubmit = async () => {
    if (!selectedTask) return;
    const missing = metrics.filter(
      (metric) =>
        typeof scoreDrafts[metric.key] !== "number" ||
        !reasonDrafts[metric.key]?.trim()
    );
    if (missing.length > 0) {
      setMessage(
        `请完成独立评分和理由：${missing.map((item) => item.name).join("、")}`
      );
      setMessageType("error");
      return;
    }
    const comments: ReviewCommentInput[] = metrics.map((metric) => ({
      dimension_key: metric.key,
      expert_score: clampScore(scoreDrafts[metric.key]),
      reason: reasonDrafts[metric.key].trim(),
    }));
    try {
      await submitBlindReview(selectedTask.reviewId, comments);
      setMessage("独立评阅已经锁定，现在可以查看四模型结果并进行对照。");
      setMessageType("success");
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "独立评阅提交失败");
      setMessageType("error");
    }
  };

  const handleComparisonSubmit = async () => {
    if (!selectedTask) return;
    const comparisons: ExpertComparisonInput[] = metrics.map((metric) => {
      const opinions = opinionsByDimension[metric.key] ?? [];
      return {
        dimension_key: metric.key,
        statement_decisions: Object.fromEntries(
          opinions.map((opinion) => [
            opinion.id,
            decisions[opinion.id] ?? "neutral",
          ])
        ),
        comparison_reason: reasonDrafts[metric.key]?.trim() ?? "",
      };
    });
    const missing = comparisons.filter(
      (item) =>
        Object.values(item.statement_decisions).includes("reject") &&
        !item.comparison_reason
    );
    if (missing.length > 0) {
      setMessage(
        `不认可智能判断时必须说明理由：${missing
          .map((item) => dimensionNames[item.dimension_key] ?? "补充维度")
          .join("、")}`
      );
      setMessageType("error");
      return;
    }
    try {
      await submitReview(selectedTask.reviewId, comparisons);
      setMessage("专家对照复核已经提交并锁定。");
      setMessageType("success");
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "对照复核提交失败");
      setMessageType("error");
    }
  };

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-center gap-3">
              <div className="rounded-xl border border-blue-100 bg-blue-50 p-2 text-blue-700">
                <ClipboardCheck className="h-5 w-5" />
              </div>
              <div>
                <CardTitle className="text-xl">专家复核工作台</CardTitle>
                <CardDescription>
                  先独立评阅匿名稿，锁定判断后再对照四模型意见。
                </CardDescription>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant="default">专家视角</Badge>
              <Badge variant="neutral">{user.display_name ?? user.email}</Badge>
            </div>
          </div>
        </CardHeader>
      </Card>

      {message ? (
        <div
          className={cn(
            "rounded-xl border px-4 py-3 text-sm",
            messageType === "success" &&
              "border-emerald-200 bg-emerald-50 text-emerald-700",
            messageType === "error" && "border-red-200 bg-red-50 text-red-700",
            messageType === "info" && "border-blue-100 bg-blue-50 text-blue-700"
          )}
        >
          {message}
        </div>
      ) : null}

      <div className="grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
        <aside className="space-y-5 xl:sticky xl:top-24 xl:max-h-[calc(100vh-7rem)] xl:self-start xl:overflow-y-auto xl:pr-1">
          <TaskList
            tasks={tasks}
            selectedTaskId={selectedTask?.id ?? null}
            onSelect={setSelectedTaskId}
          />
          {selectedTask?.stage === "blind" ? (
            <BlindPanel
              task={selectedTask}
              metrics={metrics}
              scoreDrafts={scoreDrafts}
              reasonDrafts={reasonDrafts}
              onScoreChange={(key, score) =>
                setScoreDrafts((current) => ({ ...current, [key]: score }))
              }
              onReasonChange={(key, reason) =>
                setReasonDrafts((current) => ({ ...current, [key]: reason }))
              }
              onSubmit={handleBlindSubmit}
            />
          ) : selectedTask?.stage === "comparison" ? (
            <ComparisonPanel
              metrics={metrics}
              reasonDrafts={reasonDrafts}
              onReasonChange={(key, reason) =>
                setReasonDrafts((current) => ({ ...current, [key]: reason }))
              }
              onSubmit={handleComparisonSubmit}
            />
          ) : null}
        </aside>

        <main className="min-w-0">
          {!selectedTask ? (
            <Empty text="暂无专家复核任务。" />
          ) : (
            <div className="space-y-4">
              {selectedTask.stage !== "blind" ? (
                <div className="flex rounded-xl border border-slate-200 bg-white p-1">
                  <button
                    type="button"
                    onClick={() => setActiveView("manuscript")}
                    className={cn(
                      "flex-1 rounded-lg px-4 py-2 text-sm font-medium",
                      activeView === "manuscript"
                        ? "bg-blue-50 text-blue-800"
                        : "text-slate-600 hover:bg-slate-50"
                    )}
                  >
                    匿名稿
                  </button>
                  <button
                    type="button"
                    onClick={() => setActiveView("report")}
                    className={cn(
                      "flex-1 rounded-lg px-4 py-2 text-sm font-medium",
                      activeView === "report"
                        ? "bg-blue-50 text-blue-800"
                        : "text-slate-600 hover:bg-slate-50"
                    )}
                  >
                    四模型对照
                  </button>
                </div>
              ) : null}
              {activeView === "manuscript" ? (
                <AnonymousManuscriptReader
                  manuscript={manuscript}
                  loading={manuscriptLoading}
                  error={manuscriptError}
                />
              ) : report ? (
                <InternalReportView
                  report={report}
                  decisions={decisions}
                  readonly={selectedTask.stage === "completed"}
                  onDecisionChange={(opinionId, decision) =>
                    setDecisions((current) => ({
                      ...current,
                      [opinionId]: decision,
                    }))
                  }
                />
              ) : (
                <Empty text="暂未能加载对照报告，请稍后重试。" />
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function TaskList({
  tasks,
  selectedTaskId,
  onSelect,
}: {
  tasks: WorkspaceTask[];
  selectedTaskId: string | null;
  onSelect: (taskId: string) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>复核任务</CardTitle>
        <CardDescription>每项任务均显示当前复核阶段。</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {tasks.length === 0 ? (
          <Empty text="暂无评审任务。" />
        ) : (
          tasks.map((task) => (
            <button
              key={task.id}
              type="button"
              onClick={() => onSelect(task.id)}
              className={cn(
                "w-full rounded-xl border p-3 text-left",
                task.id === selectedTaskId
                  ? "border-blue-200 bg-blue-50"
                  : "border-slate-200 bg-white hover:bg-slate-50"
              )}
            >
              <p className="truncate text-sm font-medium text-slate-950">
                {task.title}
              </p>
              <div className="mt-2 flex items-center justify-between gap-2">
                <span className="text-xs text-slate-500">
                  {task.requiredDimensions.length} 个复核维度
                </span>
                <Badge variant="neutral">{stageLabels[task.stage]}</Badge>
              </div>
            </button>
          ))
        )}
      </CardContent>
    </Card>
  );
}

function BlindPanel({
  task,
  metrics,
  scoreDrafts,
  reasonDrafts,
  onScoreChange,
  onReasonChange,
  onSubmit,
}: {
  task: WorkspaceTask;
  metrics: ReturnType<typeof normalizeInternalDimensions>;
  scoreDrafts: Record<string, number>;
  reasonDrafts: Record<string, string>;
  onScoreChange: (key: string, score: number) => void;
  onReasonChange: (key: string, reason: string) => void;
  onSubmit: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>独立评分</CardTitle>
        <CardDescription>分数和理由提交后不可覆盖。</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {metrics.map((metric) => (
          <div key={metric.key} className="rounded-xl border p-3">
            <p className="text-sm font-medium text-slate-950">{metric.name}</p>
            <Input
              className="mt-3"
              type="number"
              min={0}
              max={100}
              step={0.5}
              placeholder="独立评分"
              value={scoreDrafts[metric.key] ?? ""}
              onChange={(event) =>
                onScoreChange(metric.key, clampScore(Number(event.target.value)))
              }
            />
            <Textarea
              className="mt-3 min-h-24"
              placeholder="填写独立判断理由"
              value={reasonDrafts[metric.key] ?? ""}
              onChange={(event) => onReasonChange(metric.key, event.target.value)}
            />
          </div>
        ))}
        <Button
          type="button"
          className="w-full"
          onClick={onSubmit}
          disabled={!task.reviewId || metrics.length === 0}
        >
          <LockKeyhole className="h-4 w-4" />
          提交并锁定独立评阅
        </Button>
      </CardContent>
    </Card>
  );
}

function ComparisonPanel({
  metrics,
  reasonDrafts,
  onReasonChange,
  onSubmit,
}: {
  metrics: ReturnType<typeof normalizeInternalDimensions>;
  reasonDrafts: Record<string, string>;
  onReasonChange: (key: string, reason: string) => void;
  onSubmit: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>对照说明</CardTitle>
        <CardDescription>
          在右侧逐条选择认可、不认可或无意见；不认可时必须说明。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {metrics.map((metric) => (
          <label key={metric.key} className="block space-y-2 text-sm">
            <span className="font-medium text-slate-700">{metric.name}</span>
            <Textarea
              placeholder="填写与四模型意见对照后的补充说明"
              value={reasonDrafts[metric.key] ?? ""}
              onChange={(event) => onReasonChange(metric.key, event.target.value)}
            />
          </label>
        ))}
        <Button type="button" className="w-full" onClick={onSubmit}>
          <Send className="h-4 w-4" />
          提交并锁定对照复核
        </Button>
      </CardContent>
    </Card>
  );
}

function mapReviewTaskToTask(item: ReviewTask): WorkspaceTask {
  return {
    id: item.review_id,
    taskId: item.task_id,
    paperId: item.paper_id,
    reviewId: item.review_id,
    title: item.paper_title ?? item.paper_id ?? item.task_id,
    status: item.status,
    stage: item.review_stage,
    requiredDimensions: item.required_dimensions,
  };
}

function Empty({ text }: { text: string }) {
  return (
    <Card>
      <CardContent className="p-8 text-center text-sm text-slate-500">
        {text}
      </CardContent>
    </Card>
  );
}
