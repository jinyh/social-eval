import { useEffect, useMemo, useState } from "react";
import { ClipboardCheck, Send } from "lucide-react";

import { assignExpert, getInternalReport, getReviewQueue, listExperts, listMyReviews, submitReview } from "@/lib/api";
import { buildReviewOpinions, buildSubmitComments, clampScore, normalizeInternalDimensions } from "@/lib/report";
import type {
  ExpertDecisionState,
  InternalReport,
  ReviewQueueItem,
  ReviewTask,
  User,
} from "@/lib/types";
import { cn } from "@/lib/utils";

import { InternalReportView } from "./InternalReportView";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Input } from "./ui/input";
import { Select } from "./ui/select";
import { Textarea } from "./ui/textarea";

type ReviewWorkspaceProps = {
  user: User;
};

type WorkspaceTask = {
  id: string;
  taskId: string;
  paperId?: string | null;
  reviewId?: string;
  title: string;
  status: string;
  lowConfidenceDimensions?: string[];
};

export function ReviewWorkspace({ user }: ReviewWorkspaceProps) {
  const isEditor = user.role === "editor";
  const [tasks, setTasks] = useState<WorkspaceTask[]>([]);
  const [experts, setExperts] = useState<User[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [selectedExpertId, setSelectedExpertId] = useState("");
  const [report, setReport] = useState<InternalReport | null>(null);
  const [message, setMessage] = useState("");
  const [decisions, setDecisions] = useState<Record<string, ExpertDecisionState>>({});
  const [scoreDrafts, setScoreDrafts] = useState<Record<string, number>>({});
  const [reasonDrafts, setReasonDrafts] = useState<Record<string, string>>({});

  const selectedTask = tasks.find((task) => task.id === selectedTaskId) ?? tasks[0];

  const refresh = async () => {
    if (isEditor) {
      const [queueItems, expertItems] = await Promise.all([getReviewQueue(), listExperts()]);
      const nextTasks = queueItems.map(mapQueueItemToTask);
      setTasks(nextTasks);
      setExperts(expertItems);
      setSelectedExpertId((current) => current || expertItems[0]?.id || "");
      setSelectedTaskId((current) => current ?? nextTasks[0]?.id ?? null);
      return;
    }
    const reviewItems = await listMyReviews();
    const nextTasks = reviewItems.map(mapReviewTaskToTask);
    setTasks(nextTasks);
    setSelectedTaskId((current) => current ?? nextTasks[0]?.id ?? null);
  };

  useEffect(() => {
    void refresh().catch(() => {
      setTasks([]);
      setExperts([]);
    });
  }, [isEditor]);

  useEffect(() => {
    if (!selectedTask?.paperId) {
      setReport(null);
      return;
    }
    let isCurrent = true;
    const paperId = selectedTask.paperId;
    const taskId = selectedTask.taskId;
    void getInternalReport(paperId, taskId)
      .then((nextReport) => {
        if (!isCurrent) return;
        if (nextReport.paper_id && nextReport.paper_id !== paperId) return;
        if (nextReport.task_id && nextReport.task_id !== taskId) return;
        setReport(nextReport);
        const metrics = normalizeInternalDimensions(nextReport);
        setScoreDrafts(Object.fromEntries(metrics.map((metric) => [metric.key, metric.score])));
        setReasonDrafts({});
        setDecisions({});
      })
      .catch(() => {
        if (isCurrent) setReport(null);
      });
    return () => {
      isCurrent = false;
    };
  }, [selectedTask?.paperId, selectedTask?.taskId]);

  const metrics = useMemo(() => normalizeInternalDimensions(report), [report]);
  const opinionsByDimension = useMemo(() => {
    if (!report?.dimensions) return {};
    return Object.fromEntries(
      report.dimensions.map((dimension, index) => {
        const metric = metrics[index];
        return [metric?.key ?? dimension.key ?? `dimension-${index + 1}`, buildReviewOpinions(dimension, index)];
      })
    );
  }, [metrics, report]);

  const handleAssign = async () => {
    if (!selectedTask || !selectedExpertId) return;
    await assignExpert(selectedTask.taskId, [selectedExpertId]);
    setMessage("已分配专家，任务队列已刷新。");
    await refresh();
  };

  const handleSubmitReview = async () => {
    if (!selectedTask?.reviewId) return;
    if (report?.paper_id && selectedTask.paperId && report.paper_id !== selectedTask.paperId) {
      setMessage("当前报告与选中任务不一致，请重新选择任务后再提交。");
      return;
    }
    if (report?.task_id && selectedTask.taskId && report.task_id !== selectedTask.taskId) {
      setMessage("当前报告任务与选中复核不一致，请重新选择任务后再提交。");
      return;
    }
    const { comments, missingRejectedReasons } = buildSubmitComments(
      metrics,
      decisions,
      opinionsByDimension,
      scoreDrafts,
      reasonDrafts
    );
    if (missingRejectedReasons.length > 0) {
      setMessage(`以下维度选择了叉，需填写修正理由：${missingRejectedReasons.join("、")}`);
      return;
    }
    await submitReview(selectedTask.reviewId, comments);
    setMessage("专家复核意见已提交。三态确认已按后端 comments 结构转译。 ");
    await refresh();
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
                <CardTitle className="text-xl">编辑/专家评审工作台</CardTitle>
                <CardDescription>统一任务队列、内部评价表、专家确认与复核提交。</CardDescription>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge variant="default">{isEditor ? "编辑视角" : "专家视角"}</Badge>
              <Badge variant="neutral">{user.display_name ?? user.email}</Badge>
            </div>
          </div>
        </CardHeader>
      </Card>

      {message ? <div className="rounded-xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-700">{message}</div> : null}

      <div className="grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
        <aside className="space-y-5 xl:sticky xl:top-24 xl:max-h-[calc(100vh-7rem)] xl:self-start xl:overflow-y-auto xl:pr-1">
          <TaskList tasks={tasks} selectedTaskId={selectedTask?.id ?? null} onSelect={setSelectedTaskId} />
          {isEditor ? (
            <EditorPanel experts={experts} selectedExpertId={selectedExpertId} onExpertChange={setSelectedExpertId} onAssign={handleAssign} />
          ) : (
            <ExpertPanel
              metrics={metrics}
              scoreDrafts={scoreDrafts}
              reasonDrafts={reasonDrafts}
              onScoreChange={(key, score) => setScoreDrafts((current) => ({ ...current, [key]: score }))}
              onReasonChange={(key, reason) => setReasonDrafts((current) => ({ ...current, [key]: reason }))}
              onSubmit={handleSubmitReview}
              disabled={!selectedTask?.reviewId || metrics.length === 0}
            />
          )}
        </aside>

        <main className="min-w-0">
          {report ? (
            <InternalReportView
              report={report}
              decisions={decisions}
              readonly={isEditor}
              onDecisionChange={(opinionId, decision) => setDecisions((current) => ({ ...current, [opinionId]: decision }))}
            />
          ) : (
            <Card>
              <CardContent className="p-10">
                <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-8 text-center text-sm text-slate-500">
                  {selectedTask?.paperId
                    ? "暂未能加载内部评价表，请确认报告已生成。"
                    : "当前任务缺少 paper_id，前端无法调用内部报告接口；后端补充该字段后会自动展示。"}
                </div>
              </CardContent>
            </Card>
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
    <Card className="h-fit">
      <CardHeader>
        <CardTitle>任务队列</CardTitle>
        <CardDescription>选择任务后在中部查看内部评价表。</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {tasks.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
            暂无评审任务。
          </div>
        ) : (
          tasks.map((task) => (
            <button
              key={task.id}
              type="button"
              onClick={() => onSelect(task.id)}
              className={cn(
                "w-full rounded-xl border p-3 text-left transition-colors",
                task.id === selectedTaskId ? "border-blue-200 bg-blue-50" : "border-slate-200 bg-white hover:bg-slate-50"
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-slate-950">{task.title}</p>
                  <p className="mt-1 text-xs text-slate-500">{task.taskId}</p>
                </div>
                <Badge variant="neutral">{task.status}</Badge>
              </div>
              {task.lowConfidenceDimensions?.length ? (
                <p className="mt-3 text-xs leading-5 text-amber-700">低置信度：{task.lowConfidenceDimensions.join("、")}</p>
              ) : null}
            </button>
          ))
        )}
      </CardContent>
    </Card>
  );
}

function EditorPanel({
  experts,
  selectedExpertId,
  onExpertChange,
  onAssign,
}: {
  experts: User[];
  selectedExpertId: string;
  onExpertChange: (expertId: string) => void;
  onAssign: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>编辑操作</CardTitle>
        <CardDescription>分配专家并查看结构化内部评价表。</CardDescription>
      </CardHeader>
      <CardContent>
        <label className="space-y-2 text-sm font-medium text-slate-700">
          专家
          <Select value={selectedExpertId} onChange={(event) => onExpertChange(event.target.value)}>
            {experts.map((expert) => (
              <option key={expert.id} value={expert.id}>
                {expert.display_name ?? expert.email}
              </option>
            ))}
          </Select>
        </label>
        <Button type="button" className="mt-10 w-full" onClick={onAssign} disabled={!selectedExpertId}>
          分配当前任务
        </Button>
        <p className="text-xs leading-5 text-slate-500">编辑端可查看三态确认位置，但不编辑专家确认状态。</p>
      </CardContent>
    </Card>
  );
}

function ExpertPanel({
  metrics,
  scoreDrafts,
  reasonDrafts,
  onScoreChange,
  onReasonChange,
  onSubmit,
  disabled,
}: {
  metrics: ReturnType<typeof normalizeInternalDimensions>;
  scoreDrafts: Record<string, number>;
  reasonDrafts: Record<string, string>;
  onScoreChange: (key: string, score: number) => void;
  onReasonChange: (key: string, reason: string) => void;
  onSubmit: () => void;
  disabled: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>专家复核提交</CardTitle>
        <CardDescription>三态确认只在前端保存，提交时转译为每维度专家分数与理由。</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {metrics.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
            暂无可提交的维度数据。
          </div>
        ) : (
          metrics.map((metric) => (
            <div key={metric.key} className="rounded-xl border border-slate-200 bg-white p-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-slate-950">{metric.name}</p>
                  <p className="text-xs text-slate-500">AI 均分 {metric.score.toFixed(1)}</p>
                </div>
                <Input
                  type="number"
                  min={0}
                  max={100}
                  step={0.5}
                  value={scoreDrafts[metric.key] ?? metric.score}
                  onChange={(event) => onScoreChange(metric.key, clampScore(Number(event.target.value)))}
                  className="w-24"
                />
              </div>
              <Textarea
                className="mt-3 min-h-20"
                placeholder="填写专家理由；选择叉时必须填写修正理由。"
                value={reasonDrafts[metric.key] ?? ""}
                onChange={(event) => onReasonChange(metric.key, event.target.value)}
              />
            </div>
          ))
        )}
        <Button type="button" className="w-full" onClick={onSubmit} disabled={disabled}>
          <Send className="h-4 w-4" />
          提交复核意见
        </Button>
      </CardContent>
    </Card>
  );
}

function mapQueueItemToTask(item: ReviewQueueItem): WorkspaceTask {
  return {
    id: item.task_id,
    taskId: item.task_id,
    paperId: item.paper_id,
    title: item.paper_title ?? item.paper_id,
    status: item.task_status ?? item.paper_status ?? "reviewing",
    lowConfidenceDimensions: item.low_confidence_dimensions,
  };
}

function mapReviewTaskToTask(item: ReviewTask): WorkspaceTask {
  return {
    id: item.review_id,
    taskId: item.task_id,
    paperId: item.paper_id,
    reviewId: item.review_id,
    title: item.paper_title ?? item.paper_id ?? item.task_id,
    status: item.status,
  };
}
