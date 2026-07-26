import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  AlertTriangle,
  ArrowLeft,
  Bell,
  ClipboardCheck,
  Download,
  FileSearch,
  ShieldCheck,
  UploadCloud,
  Users,
} from "lucide-react";

import {
  assignExpert,
  confirmEditorialAnonymization,
  continueEditorialSubmission,
  editorialDocumentUrl,
  editorialReportUrl,
  getEditorialManuscript,
  getEditorialSubmission,
  listEditorialSubmissions,
  listEditorialUnits,
  listExperts,
  listNotifications,
  markNotificationRead,
  submitEditorialDecision,
  uploadEditorialSubmission,
} from "@/lib/api";
import type {
  AnonymousManuscript,
  EditorialDecision,
  EditorialDimensionSummary,
  EditorialSubmissionDetail,
  EditorialSubmissionListItem,
  EditorialSubmissionStatusGroup,
  EditorialUnit,
  FinalDecision,
  NotificationItem,
  PositionAxisSummary,
  PreReviewDecision,
  User,
} from "@/lib/types";
import {
  localizeEvaluationText,
  localizeEvaluationValue,
} from "@/lib/evaluationLocalization";
import { cn } from "@/lib/utils";

import {
  EditorialSidebar,
  type EditorWorkspaceView,
} from "./EditorialSidebar";
import { AnonymousManuscriptReader } from "./AnonymousManuscriptReader";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "./ui/card";
import { Input } from "./ui/input";
import { Select } from "./ui/select";
import { Textarea } from "./ui/textarea";

const statusLabels: Record<string, string> = {
  queued: "排队中",
  anonymizing: "匿名化处理中",
  awaiting_anonymization_confirmation: "待确认匿名化",
  formal_check: "形式完整性检查中",
  awaiting_formal_check_confirmation: "待确认形式完整性",
  prechecking: "公共预检中",
  awaiting_precheck_confirmation: "待确认公共预检",
  journal_fit_check: "期刊适配检查中",
  awaiting_fit_confirmation: "待确认期刊适配",
  evaluating: "第一轮独立评审和第二轮交叉复核中",
  generating_opinions: "生成智能辅助综合摘要",
  expert_review: "专家复核中",
  awaiting_editor: "待编辑预审决定",
  sent_for_external_review: "已送外审",
  completed: "已完成",
  recovering: "处理失败",
};

const recommendationLabels: Record<string, string> = {
  shadow: "试运行结果",
  ready: "建议可供编辑参考",
  withheld: "建议已扣留",
};

const preReviewLabels: Record<PreReviewDecision, string> = {
  decline_without_review: "不送外审",
  revise_resubmit: "修改后重投",
  send_external_review: "送外审",
  priority_external_review: "优先送外审",
};

const finalDecisionLabels: Record<FinalDecision, string> = {
  reject: "退稿",
  major_revision: "重大修改",
  minor_accept: "小修后录用",
  direct_accept: "直接录用",
};

const dimensionNames: Record<string, string> = {
  problem_originality: "研究创新性",
  literature_insight: "现状洞察度",
  analytical_framework: "理论建构力",
  logical_coherence: "逻辑连贯性",
  conclusion_consensus: "学术共识度",
  forward_extension: "前瞻延展性",
};

const submissionStatusGroups = {
  processing: new Set<string>([
    "queued",
    "anonymizing",
    "formal_check",
    "prechecking",
    "journal_fit_check",
    "evaluating",
    "generating_opinions",
    "expert_review",
  ]),
  awaiting_action: new Set<string>([
    "awaiting_anonymization_confirmation",
    "awaiting_formal_check_confirmation",
    "awaiting_precheck_confirmation",
    "awaiting_fit_confirmation",
    "awaiting_editor",
  ]),
  completed: new Set<string>(["sent_for_external_review", "completed"]),
  failed: new Set<string>(["recovering"]),
} as const;

export type SubmissionStatusFilter = "all" | EditorialSubmissionStatusGroup;

export type SubmissionFilters = {
  keyword: string;
  status: SubmissionStatusFilter;
  submittedFrom: string;
  submittedTo: string;
};

function beijingDateKey(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "";
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

export function filterEditorialSubmissions(
  rows: EditorialSubmissionListItem[],
  filters: SubmissionFilters
): EditorialSubmissionListItem[] {
  const keyword = filters.keyword.trim().toLocaleLowerCase("zh-CN");
  return rows.filter((item) => {
    const matchesKeyword =
      !keyword ||
      (item.title ?? "").toLocaleLowerCase("zh-CN").includes(keyword) ||
      (item.external_manuscript_id ?? "")
        .toLocaleLowerCase("zh-CN")
        .includes(keyword);
    const matchesStatus =
      filters.status === "all" ||
      submissionStatusGroups[filters.status].has(item.status);
    const submittedDate = beijingDateKey(item.created_at);
    const matchesFrom =
      !filters.submittedFrom || submittedDate >= filters.submittedFrom;
    const matchesTo = !filters.submittedTo || submittedDate <= filters.submittedTo;
    return matchesKeyword && matchesStatus && matchesFrom && matchesTo;
  });
}

function formatBeijingTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "时间待确认";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

type ProgressExplanation = {
  state: "running" | "paused" | "completed";
  stageLabel: string;
  headline: string;
  detail: string;
};

type DetailTab = "overview" | "report" | "actions";

const workspaceViewLabels: Record<EditorWorkspaceView, string> = {
  dashboard: "编辑工作台",
  submissions: "投稿管理",
  new: "新建投稿",
  pending: "待处理稿件",
  notifications: "通知",
};

function initialWorkspaceView(): EditorWorkspaceView {
  if (typeof window === "undefined") return "dashboard";
  const value = new URLSearchParams(window.location.search).get("view");
  return value === "submissions" ||
    value === "new" ||
    value === "pending" ||
    value === "notifications"
    ? value
    : "dashboard";
}

function initialSubmissionId(): string | null {
  if (typeof window === "undefined") return null;
  return new URLSearchParams(window.location.search).get("submission");
}

function initialDetailTab(): DetailTab {
  if (typeof window === "undefined") return "overview";
  const value = new URLSearchParams(window.location.search).get("tab");
  return value === "report" || value === "actions" ? value : "overview";
}

function initialSidebarCollapsed(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return (
      window.localStorage?.getItem("socialeval.editor.sidebar.collapsed") === "1"
    );
  } catch {
    return false;
  }
}

function stringList(
  result: Record<string, unknown> | null | undefined,
  ...keys: string[]
): string[] {
  for (const key of keys) {
    const value = result?.[key];
    if (Array.isArray(value)) {
      const items = value.filter(
        (item): item is string => typeof item === "string" && item.trim().length > 0
      );
      if (items.length > 0) return items;
    }
  }
  return [];
}

export function describeEditorialProgress(
  detail: Pick<
    EditorialSubmissionDetail,
    | "status"
    | "anonymization_result"
    | "formal_check_result"
    | "precheck_result"
    | "fit_result"
    | "progress"
  >
): ProgressExplanation {
  const pauseConfiguration: Record<
    string,
    { result?: Record<string, unknown> | null; fallback: string }
  > = {
    awaiting_anonymization_confirmation: {
      result: detail.anonymization_result,
      fallback: "匿名化检查发现需要人工核对的残留信息。",
    },
    awaiting_formal_check_confirmation: {
      result: detail.formal_check_result,
      fallback: "形式完整性检查发现需要人工判断的边界情况。",
    },
    awaiting_precheck_confirmation: {
      result: detail.precheck_result,
      fallback: "公共预检发现需要人工确认的问题。",
    },
    awaiting_fit_confirmation: {
      result: detail.fit_result,
      fallback: "期刊适配性检查发现需要人工确认的问题。",
    },
  };
  const pause = pauseConfiguration[detail.status];
  if (pause) {
    const reasons = stringList(
      pause.result,
      "issues",
      "boundary_reasons",
      "obviously_ineligible_reasons",
      "remaining_markers",
      "reasons"
    );
    return {
      state: "paused",
      stageLabel: statusLabels[detail.status] ?? "等待编辑确认",
      headline: "流程已暂停，等待编辑确认",
      detail: `暂停原因：${reasons.join("；") || pause.fallback} 请核对后在下方填写理由并确认继续。`,
    };
  }

  if (detail.status === "completed") {
    return {
      state: "completed",
      stageLabel: "已完成",
      headline: "全部处理单元已完成",
      detail: "评价结果和报告已经生成。",
    };
  }

  const runningUnit = Math.min(
    detail.progress.completed + 1,
    Math.max(detail.progress.total, 1)
  );
  return {
    state: "running",
    stageLabel:
      statusLabels[detail.status] ?? detail.progress.stage_label ?? "处理中",
    headline: statusLabels[detail.status] ?? "正在处理",
    detail:
      detail.progress.total > 0
        ? `正在执行第 ${runningUnit} 个处理单元；当前单元完成后，已完成数量和百分比会自动更新。`
        : "任务正在排队，处理计划生成后将显示完整进度。",
  };
}

export function EditorialWorkspace({ user }: { user: User }) {
  const [units, setUnits] = useState<EditorialUnit[]>([]);
  const [unitId, setUnitId] = useState("");
  const [submissions, setSubmissions] = useState<EditorialSubmissionListItem[]>([]);
  const [submissionTotal, setSubmissionTotal] = useState(0);
  const [statusCounts, setStatusCounts] = useState<
    Record<EditorialSubmissionStatusGroup, number>
  >({
    processing: 0,
    awaiting_action: 0,
    completed: 0,
    failed: 0,
  });
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(
    initialSubmissionId
  );
  const [detail, setDetail] = useState<EditorialSubmissionDetail | null>(null);
  const [workspaceView, setWorkspaceView] =
    useState<EditorWorkspaceView>(initialWorkspaceView);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    initialSidebarCollapsed
  );
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [gateReason, setGateReason] = useState("");
  const [decisionStage, setDecisionStage] = useState<"pre_review" | "final">(
    "pre_review"
  );
  const [decision, setDecision] =
    useState<EditorialDecision>("revise_resubmit");
  const [decisionReason, setDecisionReason] = useState("");
  const [bypassExpert, setBypassExpert] = useState(false);
  const [experts, setExperts] = useState<User[]>([]);
  const [expertId, setExpertId] = useState("");
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [detailTab, setDetailTab] = useState<DetailTab>(initialDetailTab);
  const [uploadFileName, setUploadFileName] = useState("");
  const [filters, setFilters] = useState<SubmissionFilters>({
    keyword: "",
    status: "all",
    submittedFrom: "",
    submittedTo: "",
  });

  const selectedUnit = units.find((unit) => unit.id === unitId);
  const unreadNotificationCount = notifications.filter(
    (item) => !item.read_at
  ).length;
  const listOptions = useMemo(
    () => ({
      unitId,
      keyword:
        workspaceView === "dashboard" ? undefined : filters.keyword.trim(),
      statusGroup:
        workspaceView === "pending"
          ? ("awaiting_action" as const)
          : filters.status === "all"
            ? undefined
            : filters.status,
      submittedFrom:
        workspaceView === "dashboard" ? undefined : filters.submittedFrom,
      submittedTo:
        workspaceView === "dashboard" ? undefined : filters.submittedTo,
      page: workspaceView === "dashboard" ? 1 : page,
      pageSize: workspaceView === "dashboard" ? 5 : 20,
    }),
    [filters, page, unitId, workspaceView]
  );
  const refreshList = useCallback(async () => {
    if (!listOptions.unitId) return;
    const result = await listEditorialSubmissions(listOptions);
    setSubmissions(result.items);
    setSubmissionTotal(result.total);
    setStatusCounts(result.status_counts);
  }, [listOptions]);

  useEffect(() => {
    void Promise.all([listEditorialUnits(), listExperts(), listNotifications()])
      .then(([unitRows, expertRows, notificationRows]) => {
        setUnits(unitRows);
        setUnitId(unitRows[0]?.id ?? "");
        setExperts(expertRows);
        setExpertId(expertRows[0]?.id ?? "");
        setNotifications(notificationRows);
      })
      .catch(() => {
        setUnits([]);
        setExperts([]);
      });
  }, []);

  useEffect(() => {
    if (!unitId) return;
    const delay = filters.keyword.trim() ? 250 : 0;
    const timer = window.setTimeout(() => {
      void refreshList().catch(() => {
        setSubmissions([]);
        setSubmissionTotal(0);
      });
    }, delay);
    return () => window.clearTimeout(timer);
  }, [filters.keyword, refreshList, unitId]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let current = true;
    void getEditorialSubmission(selectedId)
      .then((payload) => {
        if (current) setDetail(payload);
      })
      .catch(() => {
        if (current) setDetail(null);
      });
    return () => {
      current = false;
    };
  }, [selectedId]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage?.setItem(
        "socialeval.editor.sidebar.collapsed",
        sidebarCollapsed ? "1" : "0"
      );
    } catch {
      // 无持久化存储时仍保留当前会话中的收缩状态。
    }
  }, [sidebarCollapsed]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const query = new URLSearchParams(window.location.search);
    query.set("view", workspaceView);
    if (selectedId) {
      query.set("submission", selectedId);
      query.set("tab", detailTab);
    } else {
      query.delete("submission");
      query.delete("tab");
    }
    window.history.replaceState(
      null,
      "",
      `${window.location.pathname}?${query.toString()}${window.location.hash}`
    );
  }, [detailTab, selectedId, workspaceView]);

  useEffect(() => {
    if (!selectedId) return;
    const activeStatuses = new Set([
      "queued",
      "anonymizing",
      "formal_check",
      "prechecking",
      "journal_fit_check",
      "evaluating",
      "generating_opinions",
      "recovering",
    ]);
    if (!detail || !activeStatuses.has(detail.status)) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      void Promise.all([
        getEditorialSubmission(selectedId),
        listNotifications(),
      ])
        .then(([nextDetail, notificationRows]) => {
          setDetail(nextDetail);
          setNotifications(notificationRows);
          void refreshList();
        })
        .catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [detail?.status, refreshList, selectedId]);

  const handleUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!unitId) return;
    const form = event.currentTarget;
    const fileInput = form.elements.namedItem("paper") as HTMLInputElement | null;
    const externalInput = form.elements.namedItem(
      "externalId"
    ) as HTMLInputElement | null;
    const file = fileInput?.files?.[0];
    if (!file) return;
    try {
      const result = await uploadEditorialSubmission(
        unitId,
        file,
        externalInput?.value.trim()
      );
      setMessage(`稿件已进入队列：${result.submission_id}`);
      form.reset();
      setUploadFileName("");
      setWorkspaceView("submissions");
      setFilters({
        keyword: "",
        status: "all",
        submittedFrom: "",
        submittedTo: "",
      });
      setPage(1);
      await refreshList();
      setSelectedId(result.submission_id);
      setDetailTab("overview");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "上传失败");
    }
  };

  const refreshDetail = async () => {
    if (!selectedId) return;
    setDetail(await getEditorialSubmission(selectedId));
    await refreshList();
  };

  const handleGate = async () => {
    if (!detail) return;
    try {
      if (detail.status === "awaiting_anonymization_confirmation") {
        await confirmEditorialAnonymization(
          detail.id,
          gateReason || "编辑确认匿名化结果"
        );
      } else if (detail.status === "awaiting_formal_check_confirmation") {
        await continueEditorialSubmission(detail.id, "formal_check", gateReason);
      } else if (detail.status === "awaiting_precheck_confirmation") {
        await continueEditorialSubmission(detail.id, "precheck", gateReason);
      } else if (detail.status === "awaiting_fit_confirmation") {
        await continueEditorialSubmission(detail.id, "journal_fit", gateReason);
      }
      setMessage("已记录确认，后台将从当前检查点继续。");
      setGateReason("");
      await refreshDetail();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "确认失败，请稍后重试。");
    }
  };

  const handleDecision = async () => {
    if (!detail) return;
    try {
      await submitEditorialDecision(
        detail.id,
        decision,
        decisionStage,
        decisionReason,
        bypassExpert
      );
      setMessage(
        decisionStage === "pre_review"
          ? "预审决定已提交并锁定。"
          : "终审决定已提交并锁定。"
      );
      await refreshDetail();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "决定提交失败");
    }
  };

  const handleAssignExpert = async () => {
    if (!detail || !expertId) return;
    try {
      await assignExpert(detail.task_id, [expertId]);
      setMessage("专家复核任务已分配。");
      await refreshDetail();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "专家分配失败");
    }
  };

  const changeWorkspaceView = (view: EditorWorkspaceView) => {
    setWorkspaceView(view);
    setSelectedId(null);
    setDetail(null);
    setPage(1);
    if (view === "pending") setDetailTab("actions");
  };

  const openSubmission = (
    item: EditorialSubmissionListItem,
    preferredTab?: DetailTab
  ) => {
    setSelectedId(item.id);
    setDetailTab(
      preferredTab ??
        (workspaceView === "pending"
          ? "actions"
          : item.current_report_version > 0
            ? "report"
            : "overview")
    );
  };

  return (
    <div className="flex items-start gap-5">
      <EditorialSidebar
        units={units}
        unitId={unitId}
        onUnitChange={(nextUnitId) => {
          setUnitId(nextUnitId);
          setSelectedId(null);
          setPage(1);
        }}
        activeView={workspaceView}
        onViewChange={changeWorkspaceView}
        collapsed={sidebarCollapsed}
        onCollapsedChange={setSidebarCollapsed}
        mobileOpen={mobileNavigationOpen}
        onMobileOpenChange={setMobileNavigationOpen}
        pendingCount={statusCounts.awaiting_action}
        unreadCount={unreadNotificationCount}
      />

      <main className="min-w-0 flex-1 space-y-5">
        <Card>
          <CardHeader>
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div className="flex items-center gap-3">
                <div className="rounded-xl border border-blue-100 bg-blue-50 p-2 text-blue-700">
                  <FileSearch className="h-5 w-5" />
                </div>
                <div>
                  <CardTitle className="text-xl">
                    {workspaceViewLabels[workspaceView]}
                  </CardTitle>
                  <CardDescription>
                    {selectedUnit?.name ?? "尚未分配编辑单元"}
                  </CardDescription>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="default">编辑视角</Badge>
                <Badge variant="neutral">{user.display_name ?? user.email}</Badge>
                {selectedUnit ? (
                  <Badge
                    variant={
                      selectedUnit.rollout_state === "active"
                        ? "success"
                        : "warning"
                    }
                  >
                    {selectedUnit.rollout_state === "active"
                      ? "正式启用"
                      : "试运行"}
                  </Badge>
                ) : null}
              </div>
            </div>
          </CardHeader>
        </Card>

        {message ? (
          <div className="rounded-xl border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-700">
            {message}
          </div>
        ) : null}

        {units.length === 0 ? (
          <Card>
            <CardContent className="p-10">
              <Empty text="尚未分配编辑单元，请联系管理员。" />
            </CardContent>
          </Card>
        ) : workspaceView === "dashboard" ? (
          <EditorialDashboard
            statusCounts={statusCounts}
            submissions={submissions}
            notifications={notifications}
            onOpenSubmission={(item) => {
              setWorkspaceView("submissions");
              openSubmission(item);
            }}
            onNavigate={changeWorkspaceView}
            onStatusNavigate={(status) => {
              setFilters({
                keyword: "",
                status,
                submittedFrom: "",
                submittedTo: "",
              });
              changeWorkspaceView(
                status === "awaiting_action" ? "pending" : "submissions"
              );
            }}
          />
        ) : workspaceView === "new" ? (
          <EditorialUpload
            uploadFileName={uploadFileName}
            onUploadFileNameChange={setUploadFileName}
            onSubmit={handleUpload}
          />
        ) : workspaceView === "notifications" ? (
          <EditorialNotifications
            notifications={notifications}
            onRead={async (notificationId) => {
              await markNotificationRead(notificationId);
              setNotifications((current) =>
                current.map((row) =>
                  row.id === notificationId
                    ? { ...row, read_at: new Date().toISOString() }
                    : row
                )
              );
            }}
          />
        ) : detail && selectedId ? (
          <>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setSelectedId(null);
                setDetail(null);
              }}
            >
              <ArrowLeft className="h-4 w-4" />
              返回{workspaceView === "pending" ? "待处理列表" : "投稿列表"}
            </Button>
            <SubmissionDetail
              detail={detail}
              activeTab={detailTab}
              onTabChange={setDetailTab}
              gateReason={gateReason}
              onGateReasonChange={setGateReason}
              onGate={handleGate}
              decisionStage={decisionStage}
              onDecisionStageChange={(stage) => {
                setDecisionStage(stage);
                setDecision(
                  stage === "pre_review" ? "revise_resubmit" : "major_revision"
                );
              }}
              decision={decision}
              onDecisionChange={setDecision}
              decisionReason={decisionReason}
              onDecisionReasonChange={setDecisionReason}
              bypassExpert={bypassExpert}
              onBypassExpertChange={setBypassExpert}
              onDecision={handleDecision}
              experts={experts}
              expertId={expertId}
              onExpertChange={setExpertId}
              onAssignExpert={handleAssignExpert}
            />
          </>
        ) : (
          <EditorialSubmissionList
            submissions={submissions}
            total={submissionTotal}
            page={page}
            pageSize={20}
            pendingOnly={workspaceView === "pending"}
            filters={filters}
            onFiltersChange={(nextFilters) => {
              setFilters(nextFilters);
              setPage(1);
            }}
            onPageChange={setPage}
            onOpenSubmission={openSubmission}
          />
        )}
      </main>
    </div>
  );
}

function EditorialDashboard({
  statusCounts,
  submissions,
  notifications,
  onOpenSubmission,
  onNavigate,
  onStatusNavigate,
}: {
  statusCounts: Record<EditorialSubmissionStatusGroup, number>;
  submissions: EditorialSubmissionListItem[];
  notifications: NotificationItem[];
  onOpenSubmission: (item: EditorialSubmissionListItem) => void;
  onNavigate: (view: EditorWorkspaceView) => void;
  onStatusNavigate: (status: EditorialSubmissionStatusGroup) => void;
}) {
  const statusCards = [
    ["处理中", statusCounts.processing, "processing"],
    ["待人工处理", statusCounts.awaiting_action, "awaiting_action"],
    ["已完成", statusCounts.completed, "completed"],
    ["处理失败", statusCounts.failed, "failed"],
  ] as const;
  const unread = notifications.filter((item) => !item.read_at);
  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {statusCards.map(([label, count, key]) => (
          <button
            type="button"
            key={key}
            className="rounded-2xl border border-slate-200 bg-white p-5 text-left shadow-sm transition-colors hover:border-blue-200 hover:bg-blue-50/30"
            onClick={() => onStatusNavigate(key)}
          >
            <p className="text-sm text-slate-500">{label}</p>
            <p className="mt-2 text-3xl font-semibold text-slate-950">{count}</p>
          </button>
        ))}
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(300px,0.6fr)]">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <div>
                <CardTitle>最近投稿</CardTitle>
                <CardDescription>按最后更新时间显示最近五篇。</CardDescription>
              </div>
              <Button
                type="button"
                variant="outline"
                onClick={() => onNavigate("submissions")}
              >
                查看全部
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {submissions.length === 0 ? (
              <Empty text="当前编辑单元暂无投稿。" />
            ) : (
              submissions.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  className="flex w-full items-center justify-between gap-4 rounded-xl border border-slate-200 p-4 text-left hover:bg-slate-50"
                  onClick={() => onOpenSubmission(item)}
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium text-slate-950">
                      {item.title ?? item.id}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      {item.external_manuscript_id ?? item.id} ·{" "}
                      {formatBeijingTime(item.updated_at)}
                    </p>
                  </div>
                  <Badge
                    variant={item.status === "recovering" ? "danger" : "neutral"}
                  >
                    {statusLabels[item.status] ?? "状态待确认"}
                  </Badge>
                </button>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <Bell className="h-5 w-5 text-blue-700" />
              <div>
                <CardTitle>未读通知</CardTitle>
                <CardDescription>{unread.length} 条需要查看。</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {unread.length === 0 ? (
              <Empty text="当前没有未读通知。" />
            ) : (
              unread.slice(0, 5).map((item) => (
                <button
                  type="button"
                  key={item.id}
                  className="w-full rounded-xl border border-slate-200 p-3 text-left text-sm hover:bg-slate-50"
                  onClick={() => onNavigate("notifications")}
                >
                  {notificationLabel(item.event_type)}
                </button>
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function EditorialUpload({
  uploadFileName,
  onUploadFileNameChange,
  onSubmit,
}: {
  uploadFileName: string;
  onUploadFileNameChange: (name: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <Card className="max-w-3xl">
      <CardHeader>
        <CardTitle>上传新稿件</CardTitle>
        <CardDescription>
          支持 PDF、DOCX、TXT；外部稿号在当前编辑单元内唯一。
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-5" onSubmit={onSubmit}>
          <label className="block space-y-2 text-sm font-medium text-slate-700">
            外部稿号（可选）
            <Input name="externalId" placeholder="例如 JL-2026-001" />
          </label>
          <input
            id="editorial-paper-upload"
            className="sr-only"
            name="paper"
            type="file"
            accept=".pdf,.docx,.txt"
            onChange={(event) =>
              onUploadFileNameChange(event.target.files?.[0]?.name ?? "")
            }
          />
          <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
            <UploadCloud className="mx-auto h-8 w-8 text-blue-700" />
            <label
              htmlFor="editorial-paper-upload"
              className="mt-4 inline-flex cursor-pointer items-center rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
            >
              选择稿件文件
            </label>
            <p className="mt-3 truncate text-sm text-slate-500">
              {uploadFileName || "尚未选择文件"}
            </p>
          </div>
          <Button type="submit">
            <UploadCloud className="h-4 w-4" />
            上传并开始预审
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function EditorialNotifications({
  notifications,
  onRead,
}: {
  notifications: NotificationItem[];
  onRead: (notificationId: string) => Promise<void>;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>通知中心</CardTitle>
        <CardDescription>仅显示与你当前账户有关的流程事件。</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {notifications.length === 0 ? (
          <Empty text="当前没有通知。" />
        ) : (
          notifications.map((item) => (
            <div
              key={item.id}
              className={cn(
                "flex flex-col justify-between gap-3 rounded-xl border p-4 sm:flex-row sm:items-center",
                item.read_at
                  ? "border-slate-200 bg-white"
                  : "border-blue-200 bg-blue-50/40"
              )}
            >
              <div>
                <p className="font-medium text-slate-950">
                  {notificationLabel(item.event_type)}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  {formatBeijingTime(item.created_at)}
                </p>
              </div>
              {item.read_at ? (
                <Badge variant="neutral">已读</Badge>
              ) : (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => void onRead(item.id)}
                >
                  标为已读
                </Button>
              )}
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

function EditorialSubmissionList({
  submissions,
  total,
  page,
  pageSize,
  pendingOnly,
  filters,
  onFiltersChange,
  onPageChange,
  onOpenSubmission,
}: {
  submissions: EditorialSubmissionListItem[];
  total: number;
  page: number;
  pageSize: number;
  pendingOnly: boolean;
  filters: SubmissionFilters;
  onFiltersChange: (filters: SubmissionFilters) => void;
  onPageChange: (page: number) => void;
  onOpenSubmission: (
    item: EditorialSubmissionListItem,
    preferredTab?: DetailTab
  ) => void;
}) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <CardTitle>{pendingOnly ? "待处理稿件" : "投稿列表"}</CardTitle>
            <CardDescription>
              共 {total} 篇；当前第 {page}/{pageCount} 页。
            </CardDescription>
          </div>
          {pendingOnly ? <Badge variant="warning">需要编辑操作</Badge> : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4 lg:grid-cols-[minmax(220px,1fr)_180px_160px_160px_auto]">
          <Input
            value={filters.keyword}
            onChange={(event) =>
              onFiltersChange({ ...filters, keyword: event.target.value })
            }
            placeholder="搜索投稿题目或外部稿号"
          />
          <Select
            value={pendingOnly ? "awaiting_action" : filters.status}
            disabled={pendingOnly}
            onChange={(event) =>
              onFiltersChange({
                ...filters,
                status: event.target.value as SubmissionStatusFilter,
              })
            }
          >
            <option value="all">全部状态</option>
            <option value="processing">处理中</option>
            <option value="awaiting_action">待人工处理</option>
            <option value="completed">已完成</option>
            <option value="failed">处理失败</option>
          </Select>
          <Input
            type="date"
            lang="zh-CN"
            aria-label="投稿日期起"
            value={filters.submittedFrom}
            onChange={(event) =>
              onFiltersChange({ ...filters, submittedFrom: event.target.value })
            }
          />
          <Input
            type="date"
            lang="zh-CN"
            aria-label="投稿日期止"
            value={filters.submittedTo}
            onChange={(event) =>
              onFiltersChange({ ...filters, submittedTo: event.target.value })
            }
          />
          <Button
            type="button"
            variant="outline"
            onClick={() =>
              onFiltersChange({
                keyword: "",
                status: "all",
                submittedFrom: "",
                submittedTo: "",
              })
            }
          >
            清除筛选
          </Button>
        </div>

        {submissions.length === 0 ? (
          <Empty
            text={
              pendingOnly
                ? "当前没有需要人工处理的稿件。"
                : "没有符合筛选条件的投稿。"
            }
          />
        ) : (
          <div className="overflow-hidden rounded-xl border border-slate-200">
            {submissions.map((item) => (
              <button
                type="button"
                key={item.id}
                className="grid w-full gap-3 border-b border-slate-200 p-4 text-left last:border-b-0 hover:bg-slate-50 md:grid-cols-[minmax(0,1fr)_180px_180px_auto] md:items-center"
                onClick={() =>
                  onOpenSubmission(item, pendingOnly ? "actions" : undefined)
                }
              >
                <div className="min-w-0">
                  <p className="truncate font-medium text-slate-950">
                    {item.title ?? item.id}
                  </p>
                  <p className="mt-1 truncate text-xs text-slate-500">
                    {item.external_manuscript_id ?? item.id}
                  </p>
                </div>
                <span className="text-sm text-slate-600">
                  {formatBeijingTime(item.created_at)}
                </span>
                <span className="text-sm text-slate-600">
                  {formatBeijingTime(item.updated_at)}
                </span>
                <div className="flex items-center gap-2 md:justify-end">
                  <Badge
                    variant={item.status === "recovering" ? "danger" : "neutral"}
                  >
                    {statusLabels[item.status] ?? "状态待确认"}
                  </Badge>
                  {item.current_report_version > 0 ? (
                    <Badge variant="default">
                      报告 {item.current_report_version}
                    </Badge>
                  ) : null}
                </div>
              </button>
            ))}
          </div>
        )}

        <div className="flex items-center justify-between gap-3">
          <Button
            type="button"
            variant="outline"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
          >
            上一页
          </Button>
          <span className="text-sm text-slate-500">
            第 {page} 页 / 共 {pageCount} 页
          </span>
          <Button
            type="button"
            variant="outline"
            disabled={page >= pageCount}
            onClick={() => onPageChange(page + 1)}
          >
            下一页
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

type DetailProps = {
  detail: EditorialSubmissionDetail;
  activeTab: DetailTab;
  onTabChange: (value: DetailTab) => void;
  gateReason: string;
  onGateReasonChange: (value: string) => void;
  onGate: () => void;
  decisionStage: "pre_review" | "final";
  onDecisionStageChange: (value: "pre_review" | "final") => void;
  decision: EditorialDecision;
  onDecisionChange: (value: EditorialDecision) => void;
  decisionReason: string;
  onDecisionReasonChange: (value: string) => void;
  bypassExpert: boolean;
  onBypassExpertChange: (value: boolean) => void;
  onDecision: () => void;
  experts: User[];
  expertId: string;
  onExpertChange: (value: string) => void;
  onAssignExpert: () => void;
};

function SubmissionDetail(props: DetailProps) {
  const {
    detail,
    activeTab,
    onTabChange,
    gateReason,
    onGateReasonChange,
    onGate,
    decisionStage,
    onDecisionStageChange,
    decision,
    onDecisionChange,
    decisionReason,
    onDecisionReasonChange,
    bypassExpert,
    onBypassExpertChange,
    onDecision,
    experts,
    expertId,
    onExpertChange,
    onAssignExpert,
  } = props;
  const gate =
    detail.status.startsWith("awaiting_") && detail.status !== "awaiting_editor";
  const synthesis = detail.opinions.find(
    (opinion) => opinion.opinion_type === "ai_synthesis"
  );
  const decisionOptions =
    decisionStage === "pre_review" ? preReviewLabels : finalDecisionLabels;
  const preReviewRecord = [...detail.decisions]
    .reverse()
    .find((record) => record.decision_stage === "pre_review");
  const finalRecord = detail.decisions.find(
    (record) => record.decision_stage === "final"
  );
  const canSubmitFinal =
    preReviewRecord?.final_decision === "send_external_review" ||
    preReviewRecord?.final_decision === "priority_external_review";
  const currentStageLocked =
    decisionStage === "pre_review" ? Boolean(preReviewRecord) : Boolean(finalRecord);
  const progressExplanation = describeEditorialProgress(detail);
  const [manuscript, setManuscript] =
    useState<AnonymousManuscript | null>(null);
  const [manuscriptLoading, setManuscriptLoading] = useState(false);
  const [manuscriptError, setManuscriptError] = useState("");

  useEffect(() => {
    if (activeTab !== "overview" || !detail.documents.anonymized) {
      return;
    }
    let current = true;
    setManuscriptLoading(true);
    setManuscriptError("");
    void getEditorialManuscript(detail.id)
      .then((payload) => {
        if (current) setManuscript(payload);
      })
      .catch((error) => {
        if (!current) return;
        setManuscript(null);
        setManuscriptError(
          error instanceof Error ? error.message : "匿名稿加载失败"
        );
      })
      .finally(() => {
        if (current) setManuscriptLoading(false);
      });
    return () => {
      current = false;
    };
  }, [activeTab, detail.documents.anonymized, detail.id]);

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>{detail.title ?? detail.id}</CardTitle>
              <CardDescription>
                {detail.external_manuscript_id ?? detail.id} ·{" "}
                {statusLabels[detail.status] ?? "状态待确认"}
              </CardDescription>
            </div>
            <Badge
              variant={detail.recommendation_state === "ready" ? "success" : "warning"}
            >
              {recommendationLabels[detail.recommendation_state] ?? "建议状态待确认"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <dl className="grid w-full gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
            <Metric
              label="投稿时间"
              value={formatBeijingTime(detail.created_at)}
            />
            <Metric
              label="最后更新"
              value={formatBeijingTime(detail.updated_at)}
            />
            <Metric
              label="系统稿号"
              value={detail.id}
            />
            <Metric
              label="当前报告"
              value={
                detail.current_report_version > 0
                  ? `第 ${detail.current_report_version} 版`
                  : "尚未形成正式快照"
              }
            />
          </dl>
          {activeTab === "overview" && detail.documents.original ? (
            <a
              href={editorialDocumentUrl(detail.id, "original")}
              target="_blank"
              rel="noreferrer"
            >
              <Button type="button" variant="outline">
                查看原稿
              </Button>
            </a>
          ) : null}
          {activeTab === "report" && detail.current_report_version > 0 ? (
            <>
              <a
                href={editorialReportUrl(detail.id, "pdf")}
                target="_blank"
                rel="noreferrer"
              >
                <Button type="button" variant="outline">
                  <Download className="h-4 w-4" />
                  下载打印报告
                </Button>
              </a>
              <a
                href={editorialReportUrl(detail.id, "json")}
                target="_blank"
                rel="noreferrer"
              >
                <Button type="button" variant="outline">
                  下载审计数据
                </Button>
              </a>
            </>
          ) : null}
        </CardContent>
      </Card>

      {activeTab === "overview" && detail.documents.anonymized ? (
        <AnonymousManuscriptReader
          manuscript={manuscript}
          loading={manuscriptLoading}
          error={manuscriptError}
          showRisks
        />
      ) : null}

      <div
        className="grid grid-cols-3 gap-2 rounded-xl border border-slate-200 bg-white p-2"
        role="tablist"
        aria-label="投稿详情"
      >
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "overview"}
          className={cn(
            "rounded-lg px-4 py-2 text-sm font-medium",
            activeTab === "overview"
              ? "bg-blue-600 text-white"
              : "text-slate-600 hover:bg-slate-50"
          )}
          onClick={() => onTabChange("overview")}
        >
          稿件概览
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "report"}
          className={cn(
            "rounded-lg px-4 py-2 text-sm font-medium",
            activeTab === "report"
              ? "bg-blue-600 text-white"
              : "text-slate-600 hover:bg-slate-50"
          )}
          onClick={() => onTabChange("report")}
        >
          评阅报告
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "actions"}
          className={cn(
            "rounded-lg px-4 py-2 text-sm font-medium",
            activeTab === "actions"
              ? "bg-blue-600 text-white"
              : "text-slate-600 hover:bg-slate-50"
          )}
          onClick={() => onTabChange("actions")}
        >
          处理与决定
        </button>
      </div>

      {activeTab === "overview" ? (
        <>
          <ProgressPanel
            detail={detail}
            progressExplanation={progressExplanation}
          />
          {gate ? (
            <GateActionPanel
              detail={detail}
              visible
              gateReason={gateReason}
              onGateReasonChange={onGateReasonChange}
              onGate={onGate}
            />
          ) : null}
          <GateEvidence detail={detail} />
        </>
      ) : null}

      {activeTab === "report" ? (
        <>
          <EditorialSynthesisPanel detail={detail} synthesis={synthesis?.content} />

          <PositionPanel detail={detail} />

          <SixDimensionPanel
            dimensions={detail.six_dimension_summary.dimensions}
            modelCount={detail.six_dimension_summary.model_participation.count}
            differenceCount={detail.six_dimension_summary.difference_count}
            expertCount={
              detail.six_dimension_summary.expert_review_dimension_count
            }
          />

          <ExpertReviewSummary detail={detail} />

          <DecisionHistory decisions={detail.decisions} />
        </>
      ) : null}

      {activeTab === "actions" ? (
        <>
          <GateActionPanel
            detail={detail}
            visible={gate}
            gateReason={gateReason}
            onGateReasonChange={onGateReasonChange}
            onGate={onGate}
          />
          <ExpertReviewPanel
            detail={detail}
            experts={experts}
            expertId={expertId}
            onExpertChange={onExpertChange}
            onAssign={onAssignExpert}
          />

          <EditorialDecisionPanel
            detail={detail}
            decisionStage={decisionStage}
            onDecisionStageChange={onDecisionStageChange}
            decision={decision}
            onDecisionChange={onDecisionChange}
            decisionOptions={decisionOptions}
            decisionReason={decisionReason}
            onDecisionReasonChange={onDecisionReasonChange}
            bypassExpert={bypassExpert}
            onBypassExpertChange={onBypassExpertChange}
            canSubmitFinal={canSubmitFinal}
            currentStageLocked={currentStageLocked}
            onDecision={onDecision}
          />
        </>
      ) : null}
    </div>
  );
}

function ProgressPanel({
  detail,
  progressExplanation,
}: {
  detail: EditorialSubmissionDetail;
  progressExplanation: ProgressExplanation;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>处理进度</CardTitle>
        <CardDescription>
          {progressExplanation.stageLabel}
          {detail.progress.current_dimension
            ? ` · ${
                dimensionNames[detail.progress.current_dimension] ??
                detail.progress.current_dimension
              }`
            : ""}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div
          className="h-2 overflow-hidden rounded-full bg-slate-100"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={detail.progress.percent}
        >
          <div
            className="h-full rounded-full bg-blue-600 transition-all"
            style={{ width: `${detail.progress.percent}%` }}
          />
        </div>
        <div className="mt-2 flex justify-between text-xs text-slate-500">
          <span>
            已完成 {detail.progress.completed}/{detail.progress.total} 个处理单元
          </span>
          <span>{detail.progress.percent}%</span>
        </div>
        <div
          className={cn(
            "mt-3 rounded-lg border px-3 py-2 text-sm",
            progressExplanation.state === "paused"
              ? "border-amber-200 bg-amber-50 text-amber-800"
              : progressExplanation.state === "completed"
                ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                : "border-blue-100 bg-blue-50 text-blue-800"
          )}
        >
          <p className="font-medium">{progressExplanation.headline}</p>
          <p className="mt-1">{progressExplanation.detail}</p>
        </div>
        {detail.progress.is_stalled ? (
          <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700">
            处理进度长时间未更新，请管理员检查工作进程和模型服务。
          </p>
        ) : null}
        {detail.progress.failure_detail ? (
          <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
            {detail.progress.failure_detail}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function GateActionPanel({
  detail,
  visible,
  gateReason,
  onGateReasonChange,
  onGate,
}: {
  detail: EditorialSubmissionDetail;
  visible: boolean;
  gateReason: string;
  onGateReasonChange: (reason: string) => void;
  onGate: () => void;
}) {
  if (!visible) {
    return (
      <Card>
        <CardContent className="flex items-center gap-3 p-5 text-sm text-slate-600">
          <ClipboardCheck className="h-5 w-5 text-emerald-700" />
          当前流程没有等待编辑确认的门禁。
        </CardContent>
      </Card>
    );
  }
  const isAnonymization =
    detail.status === "awaiting_anonymization_confirmation";
  return (
    <Card className="border-amber-200 bg-amber-50/40">
      <CardHeader>
        <div className="flex items-center gap-3">
          <AlertTriangle className="h-5 w-5 text-amber-700" />
          <div>
            <CardTitle>
              {isAnonymization
                ? "核对匿名稿后确认是否继续"
                : "流程需要编辑确认"}
            </CardTitle>
            <CardDescription>
              {isAnonymization
                ? "这里确认的是系统生成的匿名稿，不是确认原稿本来就符合匿名要求。"
                : "原始检查结果会保留；继续操作不会改写它。"}
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {isAnonymization ? (
          <div className="space-y-2 rounded-lg border border-amber-200 bg-white px-4 py-3 text-sm leading-6 text-amber-950">
            <p>
              请先核对本页上方“匿名稿”，确认姓名、作者单位、邮箱、电话及其他身份线索
              已经移除。
            </p>
            <p className="font-medium text-red-700">
              匿名稿仍含身份信息时不要确认；请从“新建投稿”重新上传已经人工匿名的版本。
            </p>
          </div>
        ) : null}
        <Textarea
          value={gateReason}
          onChange={(event) => onGateReasonChange(event.target.value)}
          placeholder={
            isAnonymization
              ? "例如：已逐项核对网页匿名稿，未发现姓名、单位及联系方式。"
              : "填写确认或继续理由，至少 5 个字符。"
          }
        />
        <Button
          type="button"
          onClick={onGate}
          disabled={gateReason.trim().length < 5}
        >
          {isAnonymization
            ? "确认匿名稿无身份信息并继续"
            : "确认并从检查点继续"}
        </Button>
      </CardContent>
    </Card>
  );
}

const synthesisSections = [
  ["synthesis", "综合判断"],
  ["consensus_points", "四模型共识"],
  ["disagreement_points", "四模型分歧"],
  ["priority_issues", "编辑优先核验事项"],
  ["modification_suggestions", "修改建议"],
] as const;

function EditorialSynthesisPanel({
  detail,
  synthesis,
}: {
  detail: EditorialSubmissionDetail;
  synthesis?: Record<string, unknown>;
}) {
  const ccb = detail.ccb_summary;
  const recommendation =
    detail.recommendation_state === "ready" && detail.internal_candidate_decision
      ? decisionLabel(detail.internal_candidate_decision)
      : detail.recommendation_state === "withheld"
        ? "建议已扣留，需人工处理"
        : "试运行结果，不直接形成编辑决定";
  return (
    <Card id="report-summary" className="border-blue-200 shadow-sm">
      <CardHeader>
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <CardTitle>智能辅助综合摘要</CardTitle>
            <CardDescription>
              摘要基于四模型既有评价和证据生成，不是人类审稿意见。
            </CardDescription>
          </div>
          <Badge
            variant={detail.recommendation_state === "ready" ? "success" : "warning"}
          >
            {recommendation}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Metric
            label="六维综合参考分"
            value={ccb ? ccb.final_score.toFixed(1) : "尚未生成"}
          />
          <Metric
            label="匿名模型参与"
            value={`${detail.six_dimension_summary.model_participation.count} 个`}
          />
          <Metric
            label="观点差异维度"
            value={`${detail.six_dimension_summary.difference_count} 个`}
          />
          <Metric
            label="必须专家复核"
            value={`${detail.six_dimension_summary.expert_review_dimension_count} 个`}
          />
        </dl>
        {ccb ? (
          <p className="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
            核心基础分 {ccb.base_score.toFixed(1)} · 共识封顶{" "}
            {ccb.ceiling_label} · 前瞻弱加分 {ccb.bonus_score.toFixed(1)}
          </p>
        ) : null}
        {!synthesis ? (
          <Empty text="综合摘要尚未生成。" />
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {synthesisSections.map(([key, label], index) => {
              const value = synthesis[key];
              return (
                <section
                  key={key}
                  className={cn(
                    "rounded-xl border border-slate-200 p-4",
                    index === 0 && "lg:col-span-2"
                  )}
                >
                  <p className="font-medium text-slate-950">{label}</p>
                  {Array.isArray(value) ? (
                    value.length > 0 ? (
                      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-slate-700">
                        {value.map((item, itemIndex) => (
                          <li key={`${key}-${itemIndex}`}>
                            {localizeEvaluationText(item)}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-2 text-sm text-slate-500">未提出。</p>
                    )
                  ) : (
                    <p className="mt-2 text-sm leading-7 text-slate-700">
                      {localizeEvaluationText(value ?? "尚未形成")}
                    </p>
                  )}
                </section>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ExpertReviewSummary({
  detail,
}: {
  detail: EditorialSubmissionDetail;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>专家复核意见</CardTitle>
        <CardDescription>这里只展示已提交结果，分配操作位于处理页签。</CardDescription>
      </CardHeader>
      <CardContent>
        {detail.expert_reviews.length === 0 ? (
          <Empty text="当前版本尚无专家复核意见。" />
        ) : (
          <div className="space-y-3">
            {detail.expert_reviews.map((review) => (
              <div key={review.review_id} className="rounded-xl border p-4">
                <p className="font-medium text-slate-950">
                  {localizedValue(review.status)}
                </p>
                <div className="mt-3 space-y-2">
                  {review.comments.map((comment) => (
                    <div
                      key={comment.dimension_key}
                      className="rounded-lg bg-slate-50 p-3 text-sm"
                    >
                      <p className="font-medium text-slate-950">
                        {dimensionNames[comment.dimension_key] ?? "补充维度"} ·{" "}
                        {comment.expert_score.toFixed(1)} 分
                      </p>
                      <p className="mt-1 leading-6 text-slate-600">
                        {comment.reason}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function DecisionHistory({
  decisions,
}: {
  decisions: EditorialSubmissionDetail["decisions"];
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>编辑决定记录</CardTitle>
        <CardDescription>决定提交后锁定；新的决定生成新版本。</CardDescription>
      </CardHeader>
      <CardContent>
        {decisions.length === 0 ? (
          <Empty text="当前尚无已提交的编辑决定。" />
        ) : (
          <div className="space-y-2">
            {decisions.map((record) => (
              <div
                key={record.id}
                className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm"
              >
                <p className="font-medium text-slate-950">
                  {record.decision_stage === "final"
                    ? "终审"
                    : record.decision_stage === "pre_review"
                      ? "预审"
                      : "历史预审记录"}
                  ：{decisionLabel(record.final_decision)}
                </p>
                {record.rationale ? (
                  <p className="mt-1 text-slate-600">{record.rationale}</p>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function EditorialDecisionPanel({
  detail,
  decisionStage,
  onDecisionStageChange,
  decision,
  onDecisionChange,
  decisionOptions,
  decisionReason,
  onDecisionReasonChange,
  bypassExpert,
  onBypassExpertChange,
  canSubmitFinal,
  currentStageLocked,
  onDecision,
}: {
  detail: EditorialSubmissionDetail;
  decisionStage: "pre_review" | "final";
  onDecisionStageChange: (value: "pre_review" | "final") => void;
  decision: EditorialDecision;
  onDecisionChange: (value: EditorialDecision) => void;
  decisionOptions: Record<string, string>;
  decisionReason: string;
  onDecisionReasonChange: (value: string) => void;
  bypassExpert: boolean;
  onBypassExpertChange: (value: boolean) => void;
  canSubmitFinal: boolean;
  currentStageLocked: boolean;
  onDecision: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>编辑决定</CardTitle>
        <CardDescription>
          预审决定与终审决定分别记录、分别锁定并保留审计。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-2">
          <label className="space-y-2 text-sm font-medium text-slate-700">
            决定阶段
            <Select
              value={decisionStage}
              onChange={(event) =>
                onDecisionStageChange(
                  event.target.value as "pre_review" | "final"
                )
              }
            >
              <option value="pre_review">编辑预审</option>
              <option value="final" disabled={!canSubmitFinal}>
                {canSubmitFinal ? "期刊终审" : "期刊终审（需先送外审）"}
              </option>
            </Select>
          </label>
          <label className="space-y-2 text-sm font-medium text-slate-700">
            决定类型
            <Select
              value={decision}
              onChange={(event) =>
                onDecisionChange(event.target.value as EditorialDecision)
              }
            >
              {Object.entries(decisionOptions).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </label>
        </div>
        <Textarea
          value={decisionReason}
          onChange={(event) => onDecisionReasonChange(event.target.value)}
          placeholder="填写决定依据。偏离系统建议或绕过专家门禁时为必填。"
        />
        {detail.manual_review_requested && decisionStage === "pre_review" ? (
          <label className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            <input
              type="checkbox"
              checked={bypassExpert}
              onChange={(event) => onBypassExpertChange(event.target.checked)}
            />
            我确认绕过专家复核门禁，并接受该操作进入高风险审计。
          </label>
        ) : null}
        <Button
          type="button"
          onClick={onDecision}
          disabled={
            currentStageLocked || (decisionStage === "final" && !canSubmitFinal)
          }
        >
          <ShieldCheck className="h-4 w-4" />
          {currentStageLocked ? "当前阶段决定已锁定" : "提交并锁定当前阶段决定"}
        </Button>
        <DecisionHistory decisions={detail.decisions} />
      </CardContent>
    </Card>
  );
}

function GateEvidence({ detail }: { detail: EditorialSubmissionDetail }) {
  const sections = [
    ["匿名化", detail.anonymization_status, detail.anonymization_result],
    ["形式完整性", detail.formal_check_status, detail.formal_check_result],
    ["公共预检", detail.precheck_status, detail.precheck_result],
    ["期刊适配性", detail.fit_status, detail.fit_result],
  ] as const;
  return (
    <Card>
      <CardHeader>
        <CardTitle>流程门禁与依据</CardTitle>
        <CardDescription>
          形式检查和适配性检查独立于学术质量决定。
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2">
        {sections.map(([name, status, result]) => (
          <details key={name} className="rounded-xl border border-slate-200 p-4">
            <summary className="cursor-pointer">
              <span className="font-medium text-slate-950">{name}</span>
              <span className="ml-2 text-sm text-slate-500">
                {localizedValue(status)}
              </span>
            </summary>
            <div className="mt-3">
              <ReadableObject value={result} />
            </div>
          </details>
        ))}
      </CardContent>
    </Card>
  );
}

function SixDimensionPanel({
  dimensions,
  modelCount,
  differenceCount,
  expertCount,
}: {
  dimensions: EditorialDimensionSummary[];
  modelCount: number;
  differenceCount: number;
  expertCount: number;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>六维学术评价</CardTitle>
            <CardDescription>
              {modelCount} 个匿名模型参与；发现 {differenceCount} 个观点差异维度，
              其中 {expertCount} 个必须专家复核。
            </CardDescription>
          </div>
          <Badge variant={expertCount > 0 ? "warning" : "success"}>
            四模型评价
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        {dimensions.length === 0 ? (
          <Empty text="六维结果尚未生成。" />
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {dimensions.map((dimension) => (
              <details
                key={dimension.dimension_key}
                open={dimension.difference_level === "expert_review"}
                className={cn(
                  "rounded-xl border p-4",
                  dimension.difference_level === "expert_review"
                    ? "border-amber-200 bg-amber-50/40"
                    : "border-slate-200"
                )}
              >
                <summary className="cursor-pointer list-none">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium text-slate-950">
                        {dimension.dimension_name}
                      </p>
                      <p className="mt-1 text-2xl font-semibold">
                        {dimension.mean_score.toFixed(1)}
                      </p>
                    </div>
                    <div className="text-right">
                      <Badge
                        variant={
                          dimension.difference_level === "expert_review"
                            ? "warning"
                            : "neutral"
                        }
                      >
                        {dimension.band_label}
                      </Badge>
                      <p className="mt-2 text-xs text-slate-500">
                        {dimension.difference_label}
                      </p>
                    </div>
                  </div>
                  <p className="mt-2 text-xs text-slate-500">
                    标准差 {dimension.std_score.toFixed(2)} · 可信程度{" "}
                    {dimension.confidence_label}
                  </p>
                </summary>
                <div className="mt-4 space-y-3 border-t border-slate-200 pt-4">
                  {dimension.model_results.map((model) => (
                    <div
                      key={model.model_label}
                      className="rounded-lg bg-white p-3 text-sm"
                    >
                      <div className="flex justify-between gap-3 font-medium">
                        <span>{model.model_label}</span>
                        <span>
                          {model.score.toFixed(1)} 分 · {model.band_label}
                        </span>
                      </div>
                      {model.analysis ? (
                        <p className="mt-2 leading-6 text-slate-600">
                          {model.analysis}
                        </p>
                      ) : null}
                      <Evidence value={model.evidence_quotes} />
                    </div>
                  ))}
                </div>
              </details>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PositionPanel({ detail }: { detail: EditorialSubmissionDetail }) {
  const value = detail.position_summary;
  return (
    <Card>
      <CardHeader>
        <CardTitle>五轴位置归属度</CardTitle>
        <CardDescription>
          判断知识在中国法学自主知识体系中的位置归属，不评价论文质量。
        </CardDescription>
      </CardHeader>
      <CardContent>
        {!value ? (
          <Empty text="五轴结果尚未生成。" />
        ) : (
          <div className="space-y-4">
            <div className="flex items-end justify-between gap-3">
              <div>
                <p className="text-4xl font-semibold text-slate-950">
                  {value.total_score}
                  <span className="text-base font-normal text-slate-500"> / 10</span>
                </p>
                <p className="mt-1 text-sm text-slate-600">
                  {value.strength_label} · {value.agreement_label}
                </p>
              </div>
              {value.review_required ? (
                <Badge variant="warning">需要人工核验</Badge>
              ) : (
                <Badge variant="neutral">内部参考</Badge>
              )}
            </div>
            {value.conflict_with_precheck ? (
              <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-800">
                <AlertTriangle className="mr-2 inline h-4 w-4" />
                {value.conflict_message}
              </div>
            ) : null}
            <div className="space-y-3">
              {value.axes.map((axis) => (
                <PositionAxis key={axis.axis_key} axis={axis} />
              ))}
            </div>
            <p className="text-xs leading-5 text-slate-500">{value.notice}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PositionAxis({ axis }: { axis: PositionAxisSummary }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm">
      <div className="flex justify-between gap-3">
        <div>
          <p className="font-medium text-slate-950">{axis.axis_name}</p>
          <p className="mt-1 text-slate-600">{axis.focus_label}</p>
        </div>
        <span>
          {axis.score} / 2{axis.has_model_difference ? " · 两模型有差异" : ""}
        </span>
      </div>
      <p className="mt-3 leading-6 text-slate-700">{axis.guiding_question}</p>
      <details className="mt-3 rounded-lg border border-slate-200 bg-white p-3">
        <summary className="cursor-pointer font-medium text-slate-700">
          查看原文依据
        </summary>
        <Evidence value={axis.evidence_quotes} />
      </details>
    </div>
  );
}

function ExpertReviewPanel({
  detail,
  experts,
  expertId,
  onExpertChange,
  onAssign,
}: {
  detail: EditorialSubmissionDetail;
  experts: User[];
  expertId: string;
  onExpertChange: (value: string) => void;
  onAssign: () => void;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <Users className="h-5 w-5 text-blue-700" />
          <div>
            <CardTitle>专家复核</CardTitle>
            <CardDescription>
              专家先独立评阅，提交锁定后再查看四模型结果。
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-col gap-3 md:flex-row">
          <Select value={expertId} onChange={(event) => onExpertChange(event.target.value)}>
            {experts.map((expert) => (
              <option key={expert.id} value={expert.id}>
                {expert.display_name ?? expert.email}
              </option>
            ))}
          </Select>
          <Button type="button" onClick={onAssign} disabled={!expertId}>
            分配当前稿件
          </Button>
        </div>
        {detail.expert_reviews.length === 0 ? (
          <Empty
            text={
              detail.manual_review_requested
                ? "当前稿件需要专家复核，尚未分配专家。"
                : "当前稿件没有强制专家复核任务。"
            }
          />
        ) : (
          detail.expert_reviews.map((review) => (
            <div key={review.review_id} className="rounded-xl border p-4">
              <p className="font-medium text-slate-950">
                {localizedValue(review.status)}
              </p>
              <div className="mt-3 space-y-3">
                {review.comments.map((comment) => (
                  <div key={comment.dimension_key} className="rounded-lg bg-slate-50 p-3">
                    <p className="font-medium">
                      {dimensionNames[comment.dimension_key] ?? "补充维度"} · 专家评分{" "}
                      {comment.expert_score.toFixed(1)}
                    </p>
                    <p className="mt-1 text-sm leading-6 text-slate-600">
                      {comment.reason}
                    </p>
                    {comment.comparison_reason ? (
                      <p className="mt-1 text-sm leading-6 text-blue-700">
                        对照说明：{comment.comparison_reason}
                      </p>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

function ReadableObject({ value }: { value: unknown }) {
  if (!value) return <p className="text-sm text-slate-500">暂无详情。</p>;
  if (typeof value !== "object")
    return <p className="text-sm text-slate-600">{localizedValue(value)}</p>;
  const entries = Object.entries(value as Record<string, unknown>).filter(
    ([key]) => key !== "raw"
  );
  return (
    <dl className="space-y-2 text-sm">
      {entries.map(([key, item]) => (
        <div key={key}>
          <dt className="font-medium text-slate-700">{fieldLabel(key)}</dt>
          <dd className="mt-1 leading-6 text-slate-600">
            {Array.isArray(item)
              ? item.map(localizedValue).join("；") || "无"
              : typeof item === "object"
                ? "详见审计数据"
                : localizedValue(item)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function fieldLabel(key: string) {
  return (
    {
      status: "状态",
      conclusion: "结论",
      reasons: "理由",
      evidence_quotes: "原文证据",
      issues: "发现的问题",
      character_count: "可解析字符数",
      has_section_structure: "识别到论文结构",
      has_reference_markers: "识别到引注线索",
      requires_editor_confirmation: "需要编辑确认",
      notice: "说明",
      boundary_status: "边界状态",
      boundary_reasons: "边界理由",
      obviously_ineligible_reasons: "明显不适格理由",
      recommendation: "处理建议",
      enter_six_dimension_review: "是否进入六维评审",
      triggered_signals: "触发信号",
      requires_manual_confirmation: "需要人工确认",
      text_quality_gate: "文本质量检查",
      project_scope_precheck: "项目范围预检",
      confidence: "可信程度",
      policy_version: "匿名规则版本",
      document_version: "匿名稿版本",
      redaction_counts: "隐去统计",
      remaining_markers: "剩余可疑标记",
      risk_flags: "核验提示",
      omitted_content_types: "未展示内容类型",
      human_confirmed: "人工确认",
      auto_confirmed: "模型自动确认",
      confirmed_by_model: "匿名检测模型",
      confirmed_at: "匿名处理时间",
      ai_anonymization: "模型匿名审计",
    }[key] ?? "补充信息"
  );
}

function localizedValue(value: unknown): string {
  return localizeEvaluationValue(value);
}

function decisionLabel(value: EditorialDecision) {
  return (
    preReviewLabels[value as PreReviewDecision] ??
    finalDecisionLabels[value as FinalDecision] ??
    "历史决定"
  );
}

function notificationLabel(eventType: string): string {
  return (
    {
      expert_review_assigned: "有新的专家复核任务",
      editorial_review_ready: "智能辅助预审材料已就绪",
      editorial_review_failed: "稿件处理失败，等待恢复",
      anonymization_auto_processed: "GLM-5.2 已自动完成匿名检测与处理",
      expert_review_submitted: "专家复核已提交",
      responsible_editor_transferred: "责任编辑任务已转移",
    }[eventType] ?? "有新的流程通知"
  );
}

function Evidence({ value }: { value: unknown }) {
  const list = Array.isArray(value)
    ? value.flatMap((item) =>
        typeof item === "string"
          ? [item]
          : Array.isArray(item)
            ? item.filter((nested): nested is string => typeof nested === "string")
            : []
      )
    : [];
  if (list.length === 0)
    return <p className="mt-2 text-xs text-amber-700">未提供可核验原文证据。</p>;
  return (
    <ul className="mt-2 list-disc space-y-1 pl-5 text-xs leading-5 text-slate-600">
      {list.slice(0, 4).map((item, index) => (
        <li key={`${item}-${index}`}>{item}</li>
      ))}
    </ul>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="mt-1 text-sm font-medium text-slate-950">{value}</dd>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-500">
      {text}
    </div>
  );
}
