import { FormEvent, useEffect, useState } from "react";
import {
  AlertTriangle,
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
  EditorialDecision,
  EditorialDimensionSummary,
  EditorialSubmissionDetail,
  EditorialSubmissionListItem,
  EditorialUnit,
  FinalDecision,
  NotificationItem,
  PositionAxisSummary,
  PreReviewDecision,
  User,
} from "@/lib/types";
import { cn } from "@/lib/utils";

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

export function EditorialWorkspace({ user }: { user: User }) {
  const [units, setUnits] = useState<EditorialUnit[]>([]);
  const [unitId, setUnitId] = useState("");
  const [submissions, setSubmissions] = useState<EditorialSubmissionListItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EditorialSubmissionDetail | null>(null);
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

  const selectedUnit = units.find((unit) => unit.id === unitId);

  const refreshList = async (nextUnitId = unitId) => {
    if (!nextUnitId) return;
    const rows = await listEditorialSubmissions(nextUnitId);
    setSubmissions(rows);
    setSelectedId((current) =>
      rows.some((item) => item.id === current) ? current : rows[0]?.id ?? null
    );
  };

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
    void refreshList(unitId).catch(() => setSubmissions([]));
  }, [unitId]);

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
        listEditorialSubmissions(unitId),
        listNotifications(),
      ])
        .then(([nextDetail, rows, notificationRows]) => {
          setDetail(nextDetail);
          setSubmissions(rows);
          setNotifications(notificationRows);
        })
        .catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [detail?.status, selectedId, unitId]);

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
      await refreshList();
      setSelectedId(result.submission_id);
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

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-center gap-3">
              <div className="rounded-xl border border-blue-100 bg-blue-50 p-2 text-blue-700">
                <FileSearch className="h-5 w-5" />
              </div>
              <div>
                <CardTitle className="text-xl">期刊编辑预审工作台</CardTitle>
                <CardDescription>
                  从形式检查、学术评价和专家复核到两级编辑决定。
                </CardDescription>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="default">编辑视角</Badge>
              <Badge variant="neutral">{user.display_name ?? user.email}</Badge>
              {selectedUnit ? (
                <Badge
                  variant={
                    selectedUnit.rollout_state === "active" ? "success" : "warning"
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

      {notifications.some((item) => !item.read_at) ? (
        <Card>
          <CardHeader>
            <CardTitle>待读通知</CardTitle>
            <CardDescription>仅显示与你当前账户有关的流程事件。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {notifications
              .filter((item) => !item.read_at)
              .slice(0, 5)
              .map((item) => (
                <button
                  type="button"
                  key={item.id}
                  className="flex w-full items-center justify-between rounded-xl border border-slate-200 p-3 text-left text-sm"
                  onClick={async () => {
                    await markNotificationRead(item.id);
                    setNotifications((current) =>
                      current.map((row) =>
                        row.id === item.id
                          ? { ...row, read_at: new Date().toISOString() }
                          : row
                      )
                    );
                  }}
                >
                  <span>{notificationLabel(item.event_type)}</span>
                  <span className="text-xs text-slate-500">标为已读</span>
                </button>
              ))}
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-5 xl:grid-cols-[370px_minmax(0,1fr)]">
        <aside className="space-y-5 xl:sticky xl:top-24 xl:max-h-[calc(100vh-7rem)] xl:self-start xl:overflow-y-auto xl:pr-1">
          <Card>
            <CardHeader>
              <CardTitle>编辑单元与上传</CardTitle>
              <CardDescription>外部稿号在当前编辑单元内唯一。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Select value={unitId} onChange={(event) => setUnitId(event.target.value)}>
                {units.map((unit) => (
                  <option key={unit.id} value={unit.id}>
                    {unit.name}
                  </option>
                ))}
              </Select>
              {units.length === 0 ? (
                <Empty text="尚未分配编辑单元，请联系管理员。" />
              ) : (
                <form className="space-y-3" onSubmit={handleUpload}>
                  <Input name="externalId" placeholder="外部稿号（可选）" />
                  <Input name="paper" type="file" accept=".pdf,.docx,.txt" />
                  <Button className="w-full" type="submit">
                    <UploadCloud className="h-4 w-4" />
                    上传并开始预审
                  </Button>
                </form>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>投稿列表</CardTitle>
              <CardDescription>同一编辑单元成员可见。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {submissions.length === 0 ? (
                <Empty text="当前编辑单元暂无投稿。" />
              ) : (
                submissions.map((item) => (
                  <button
                    type="button"
                    key={item.id}
                    onClick={() => setSelectedId(item.id)}
                    className={cn(
                      "w-full rounded-xl border p-3 text-left transition-colors",
                      selectedId === item.id
                        ? "border-blue-200 bg-blue-50"
                        : "border-slate-200 bg-white hover:bg-slate-50"
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-slate-950">
                          {item.title ?? item.id}
                        </p>
                        <p className="mt-1 text-xs text-slate-500">
                          {item.external_manuscript_id ?? item.id}
                        </p>
                      </div>
                      <Badge
                        variant={item.status === "recovering" ? "danger" : "neutral"}
                      >
                        {statusLabels[item.status] ?? "状态待确认"}
                      </Badge>
                    </div>
                  </button>
                ))
              )}
            </CardContent>
          </Card>
        </aside>

        <main className="min-w-0">
          {detail ? (
            <SubmissionDetail
              detail={detail}
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
          ) : (
            <Card>
              <CardContent className="p-10">
                <Empty text="选择一篇投稿查看预审进度和报告。" />
              </CardContent>
            </Card>
          )}
        </main>
      </div>
    </div>
  );
}

type DetailProps = {
  detail: EditorialSubmissionDetail;
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
          {detail.documents.original ? (
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
          {detail.documents.anonymized ? (
            <a
              href={editorialDocumentUrl(detail.id, "anonymized")}
              target="_blank"
              rel="noreferrer"
            >
              <Button type="button" variant="outline">
                查看匿名稿
              </Button>
            </a>
          ) : null}
          {detail.decisions.length > 0 ? (
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

      <Card>
        <CardHeader>
          <CardTitle>处理进度</CardTitle>
          <CardDescription>
            {detail.progress.stage_label}
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

      {gate ? (
        <Card className="border-amber-200 bg-amber-50/40">
          <CardHeader>
            <div className="flex items-center gap-3">
              <AlertTriangle className="h-5 w-5 text-amber-700" />
              <div>
                <CardTitle>流程需要编辑确认</CardTitle>
                <CardDescription>
                  原始检查结果会保留；继续操作不会改写它。
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <Textarea
              value={gateReason}
              onChange={(event) => onGateReasonChange(event.target.value)}
              placeholder="填写确认或继续理由，至少 5 个字符。"
            />
            <Button
              type="button"
              onClick={onGate}
              disabled={
                detail.status !== "awaiting_anonymization_confirmation" &&
                gateReason.trim().length < 5
              }
            >
              确认并从检查点继续
            </Button>
          </CardContent>
        </Card>
      ) : null}

      <GateEvidence detail={detail} />

      <Card>
        <CardHeader>
          <CardTitle>智能辅助综合摘要</CardTitle>
          <CardDescription>
            摘要基于四模型既有评价和证据生成，不是人类审稿意见。
          </CardDescription>
        </CardHeader>
        <CardContent>
          {synthesis ? (
            <OpinionContent content={synthesis.content} />
          ) : (
            <Empty text="综合摘要尚未生成。" />
          )}
        </CardContent>
      </Card>

      <SixDimensionPanel
        dimensions={detail.six_dimension_summary.dimensions}
        modelCount={detail.six_dimension_summary.model_participation.count}
        differenceCount={detail.six_dimension_summary.difference_count}
        expertCount={detail.six_dimension_summary.expert_review_dimension_count}
      />

      <div className="grid gap-5 lg:grid-cols-2">
        <CcbPanel detail={detail} />
        <PositionPanel detail={detail} />
      </div>

      <ExpertReviewPanel
        detail={detail}
        experts={experts}
        expertId={expertId}
        onExpertChange={onExpertChange}
        onAssign={onAssignExpert}
      />

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
            disabled={currentStageLocked || (decisionStage === "final" && !canSubmitFinal)}
          >
            <ShieldCheck className="h-4 w-4" />
            {currentStageLocked ? "当前阶段决定已锁定" : "提交并锁定当前阶段决定"}
          </Button>
          {detail.decisions.length > 0 ? (
            <div className="space-y-2">
              {detail.decisions.map((record) => (
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
          ) : null}
        </CardContent>
      </Card>
    </div>
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

function CcbPanel({ detail }: { detail: EditorialSubmissionDetail }) {
  const value = detail.ccb_summary;
  return (
    <Card>
      <CardHeader>
        <CardTitle>六维综合参考分</CardTitle>
        <CardDescription>核心维度加权、学术共识封顶和前瞻弱加分。</CardDescription>
      </CardHeader>
      <CardContent>
        {!value ? (
          <Empty text="综合参考分尚未生成。" />
        ) : (
          <div className="space-y-4">
            <p className="text-4xl font-semibold text-slate-950">
              {value.final_score.toFixed(1)}
            </p>
            <dl className="grid grid-cols-3 gap-2 text-sm">
              <Metric label="核心基础分" value={value.base_score.toFixed(1)} />
              <Metric label="前瞻弱加分" value={value.bonus_score.toFixed(1)} />
              <Metric label="共识封顶" value={value.ceiling_label} />
            </dl>
            <p className="text-xs leading-5 text-slate-500">{value.notice}</p>
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
        <CardDescription>主视图只显示总分，明细按需展开。</CardDescription>
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
            <details className="rounded-xl border border-slate-200 p-4">
              <summary className="cursor-pointer font-medium text-slate-950">
                查看五轴归属依据
              </summary>
              <div className="mt-4 space-y-3">
                {value.axes.map((axis) => (
                  <PositionAxis key={axis.axis_key} axis={axis} />
                ))}
              </div>
            </details>
            <p className="text-xs leading-5 text-slate-500">{value.notice}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PositionAxis({ axis }: { axis: PositionAxisSummary }) {
  return (
    <div className="rounded-lg bg-slate-50 p-3 text-sm">
      <div className="flex justify-between gap-3">
        <span className="font-medium text-slate-950">{axis.axis_name}</span>
        <span>
          {axis.score} / 2{axis.has_model_difference ? " · 两模型有差异" : ""}
        </span>
      </div>
      <Evidence value={axis.evidence_quotes} />
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

function OpinionContent({ content }: { content: Record<string, unknown> }) {
  return (
    <div className="space-y-3 text-sm leading-7 text-slate-700">
      {Object.entries(content).map(([key, value]) => (
        <section key={key}>
          <p className="font-medium text-slate-950">{opinionFieldLabel(key)}</p>
          {Array.isArray(value) ? (
            <ul className="list-disc pl-5">
              {value.map((item, index) => (
                <li key={`${key}-${index}`}>{String(item)}</li>
              ))}
            </ul>
          ) : (
            <p>{typeof value === "object" ? "详见审计数据" : String(value)}</p>
          )}
        </section>
      ))}
    </div>
  );
}

function opinionFieldLabel(key: string) {
  return (
    {
      synthesis: "综合判断",
      summary: "总评",
      strengths: "主要优点",
      issues: "主要问题",
      consensus_points: "四模型共识",
      disagreement_points: "四模型分歧",
      priority_issues: "优先核验",
      modification_suggestions: "修改建议",
    }[key] ?? "补充信息"
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
      confidence: "可信程度",
    }[key] ?? "补充信息"
  );
}

function localizedValue(value: unknown): string {
  const text = String(value ?? "");
  return (
    {
      pass: "通过",
      passed: "通过",
      boundary: "边界，需确认",
      boundary_review: "边界复核",
      reject: "不通过",
      pending: "待处理",
      confirmed: "已确认",
      needs_confirmation: "需要确认",
      comparison: "已完成独立评阅，正在对照",
      submitted: "专家复核已完成",
      returned: "已退回修改",
      high: "高",
      medium: "中等",
      low: "较低",
      critical: "很低",
      true: "是",
      false: "否",
    }[text] ?? (text || "待确认")
  );
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
