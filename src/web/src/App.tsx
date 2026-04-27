import { FormEvent, useEffect, useState } from "react";

import {
  assignExpert,
  createInvitation,
  exportSimpleReport,
  getCurrentUser,
  getInternalReport,
  getPaperStatus,
  getPublicReport,
  getReviewQueue,
  listExperts,
  listMyReviews,
  listPapers,
  listUsers,
  login,
  logout,
  submitReview,
  uploadPaper,
} from "./lib/api";
import type {
  DimensionScore,
  InternalReport,
  ModelDetail,
  PaperListItem,
  PaperStatus,
  PublicReport,
  ReviewCommentPayload,
  ReviewQueueItem,
  ReviewTask,
  User,
} from "./lib/types";
import "./styles.css";

type AppProps = {
  initialUser?: User | null;
};

type ReviewDecision = "agree" | "reject" | "neutral";

type DimensionGridState = Record<string, string>;

const REVIEW_DECISION_LABELS: Record<ReviewDecision, string> = {
  agree: "✓",
  reject: "×",
  neutral: "−",
};

const REVIEW_DECISION_TEXT: Record<ReviewDecision, string> = {
  agree: "采纳 AI 意见",
  reject: "不采纳 AI 意见",
  neutral: "无意见",
};

function LoginForm({ onLoggedIn }: { onLoggedIn: (user: User) => void }) {
  const [email, setEmail] = useState("submitter@example.com");
  const [password, setPassword] = useState("secret123");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const user = await login(email, password);
      setError(null);
      onLoggedIn(user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    }
  };

  return (
    <section className="panel login-panel">
      <p className="eyebrow">SocialEval V2.40</p>
      <h1>选择入口后登录</h1>
      <div className="portal-grid compact">
        <article className="portal-card">
          <span className="portal-index">01</span>
          <h2>普通学生 / 投稿人入口</h2>
          <p>上传论文，查看面向学生的综合反馈、三方意见差异和简洁报告。</p>
        </article>
        <article className="portal-card">
          <span className="portal-index">02</span>
          <h2>编辑 / 专家入口</h2>
          <p>查看类似 PDF 评审包的逐维意见，并对专家复核意见打勾、打叉或保留无意见。</p>
        </article>
      </div>
      <form className="stack" onSubmit={handleSubmit}>
        <label>
          邮箱
          <input value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <label>
          密码
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <button type="submit">进入系统</button>
        {error ? <p className="error">{error}</p> : null}
      </form>
    </section>
  );
}

function formatScore(score: number | undefined | null): string {
  return typeof score === "number" ? score.toFixed(1) : "-";
}

function getStatusLabel(paperStatus: string | undefined | null): string {
  const statusMap: Record<string, string> = {
    pending: "待处理",
    processing: "处理中",
    prechecking: "准入检查中",
    precheck_failed: "准入检查未通过",
    evaluating: "评价中",
    reviewing: "专家复核中",
    completed: "已完成",
    failed: "处理失败",
    recovering: "等待恢复",
  };
  return paperStatus ? statusMap[paperStatus] || paperStatus : "未知";
}

function getConfidenceLabel(dim: DimensionScore): string {
  return dim.ai.is_high_confidence === false ? "需复核" : "稳定";
}

function getReportTitle(report: PublicReport | InternalReport): string {
  return report.paper_title ?? report.title ?? "未命名论文";
}

function toText(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map((item) => toText(item)).filter(Boolean).join("；") || "-";
  }
  if (value && typeof value === "object") {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    return formatScore(value);
  }
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  return "-";
}

function modelLabel(index: number): string {
  return ["模型一", "模型二", "模型三"][index] ?? `模型${index + 1}`;
}

function getModelDetails(dimension: DimensionScore): ModelDetail[] {
  if (dimension.ai.model_details?.length) {
    return dimension.ai.model_details;
  }
  return Object.entries(dimension.ai.model_scores ?? {}).map(([modelName, score]) => ({
    model_name: modelName,
    score,
  }));
}

function PortalIntro({ user }: { user: User }) {
  const isPublicPortal = user.role === "submitter";
  const isProfessionalPortal = user.role === "editor" || user.role === "expert" || user.role === "admin";
  return (
    <div className="portal-grid">
      <article className={`portal-card ${isPublicPortal ? "active" : ""}`}>
        <span className="portal-index">01</span>
        <h2>普通学生 / 投稿人入口</h2>
        <p>只展示总评、维度摘要、三方意见差异和专家编辑意见，不暴露底层模型名称。</p>
      </article>
      <article className={`portal-card ${isProfessionalPortal ? "active" : ""}`}>
        <span className="portal-index">02</span>
        <h2>编辑 / 专家入口</h2>
        <p>保留 PDF 式逐维评审包，编辑可分配复核，专家可逐项标记采纳、否定或无意见。</p>
      </article>
    </div>
  );
}

function SimpleScoreCard({ dimensions }: { dimensions: DimensionScore[] }) {
  return (
    <div className="score-card">
      {dimensions.map((dim) => (
        <div key={dim.key} className="score-row">
          <div className="score-header">
            <div>
              <span className="dimension-name">{dim.name_zh}</span>
              <small>{dim.name_en}</small>
            </div>
            <div className="score-meta">
              <span className="dimension-score">{formatScore(dim.ai.mean_score)} 分</span>
              <span className={dim.ai.is_high_confidence === false ? "risk-chip" : "ok-chip"}>
                {getConfidenceLabel(dim)}
              </span>
            </div>
          </div>
          <p className="dimension-summary">{dim.summary || "暂无总结"}</p>
          <small>标准差 {formatScore(dim.ai.std_score)} · 权重 {Math.round((dim.weight ?? 0) * 100)}%</small>
        </div>
      ))}
    </div>
  );
}

function StudentSummary({ report }: { report: PublicReport }) {
  const unstableDimensions = report.dimensions.filter((dim) => dim.ai.is_high_confidence === false);
  const highestSpread = [...report.dimensions].sort(
    (left, right) => (right.ai.std_score ?? 0) - (left.ai.std_score ?? 0)
  )[0];
  const expertReasons = (report.expert_reviews ?? []).flatMap((review) =>
    review.comments.map((comment) => comment.reason).filter(Boolean)
  );

  return (
    <section className="report-conclusion student-summary">
      <h5>学生版总结</h5>
      <p>
        三方意见的综合总分为 {formatScore(report.weighted_total)} 分，系统结论为
        {report.conclusion ?? "待专家确认"}。
      </p>
      <p>
        分歧主要集中在
        {unstableDimensions.length > 0
          ? unstableDimensions.map((dim) => dim.name_zh).join("、")
          : highestSpread?.name_zh ?? "暂无明显分歧"}
        ，其中最大标准差为 {formatScore(highestSpread?.ai.std_score)}。
      </p>
      <p>
        专家/编辑意见：{expertReasons.length > 0 ? expertReasons.slice(0, 3).join("；") : "暂无额外意见"}。
      </p>
    </section>
  );
}

function SubmitterDashboard() {
  const [papers, setPapers] = useState<PaperListItem[]>([]);
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null);
  const [status, setStatus] = useState<PaperStatus | null>(null);
  const [report, setReport] = useState<PublicReport | null>(null);
  const [message, setMessage] = useState<string>("");
  const [downloading, setDownloading] = useState<boolean>(false);

  const refreshPapers = async () => setPapers(await listPapers());

  useEffect(() => {
    void refreshPapers().catch(() => setPapers([]));
  }, []);

  useEffect(() => {
    if (papers.length > 0 && !selectedPaperId) {
      setSelectedPaperId(papers[0].paper_id);
    }
  }, [papers, selectedPaperId]);

  useEffect(() => {
    if (selectedPaperId) {
      void loadReport(selectedPaperId);
    }
  }, [selectedPaperId]);

  const loadReport = async (paperId: string) => {
    setReport(null);
    try {
      const nextStatus = await getPaperStatus(paperId);
      setStatus(nextStatus);
    } catch (err) {
      setStatus(null);
      setReport(null);
      setMessage(err instanceof Error ? err.message : "报告读取失败");
      return;
    }
    try {
      setReport(await getPublicReport(paperId));
      setMessage("");
    } catch {
      setReport(null);
    }
  };

  const handleUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const input = form.elements.namedItem("paper") as HTMLInputElement | null;
    const file = input?.files?.[0];
    if (!file) {
      setMessage("请选择 PDF、DOCX 或 TXT 文件");
      return;
    }
    try {
      const payload = await uploadPaper(file);
      setMessage(`上传成功：${payload.paper_id}`);
      setSelectedPaperId(payload.paper_id);
      await refreshPapers();
      form.reset();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "上传失败");
    }
  };

  const handleDownloadReport = async () => {
    if (!selectedPaperId) return;
    setDownloading(true);
    try {
      const blob = await exportSimpleReport(selectedPaperId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `report-${selectedPaperId}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "下载失败");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="dashboard-grid submitter-view">
      <section className="panel upload-section">
        <p className="eyebrow">学生 / 投稿人</p>
        <h2>普通学生 / 投稿人入口</h2>
        <p className="muted">当前固定使用 V2.40 评审框架和三方综合评审，不需要手动选择模型。</p>
        <form onSubmit={handleUpload} className="stack">
          <input name="paper" type="file" accept=".pdf,.docx,.txt" />
          <button type="submit">上传论文</button>
        </form>
        {message ? <p className="info-message">{message}</p> : null}
      </section>

      <section className="panel papers-section">
        <h3>我的论文</h3>
        <ul className="list paper-list">
          {papers.length === 0 ? (
            <li className="empty-hint">暂无论文，请上传</li>
          ) : (
            papers.map((paper) => (
              <li
                key={paper.paper_id}
                className={paper.paper_id === selectedPaperId ? "selected" : ""}
                onClick={() => setSelectedPaperId(paper.paper_id)}
              >
                <div className="paper-title">{paper.title ?? paper.original_filename}</div>
                <span className={`paper-status status-${paper.paper_status}`}>
                  {getStatusLabel(paper.paper_status)}
                </span>
              </li>
            ))
          )}
        </ul>
      </section>

      <section className="panel results-section">
        <h3>学生版评价结果</h3>
        {status ? (
          <div className="status-strip">
            <span>论文：{getStatusLabel(status.paper_status)}</span>
            <span>任务：{getStatusLabel(status.task_status)}</span>
            <span>准入：{status.precheck_status ?? "待检查"}</span>
          </div>
        ) : null}
        {report ? (
          <div className="report-content">
            <div className="report-header">
              <h4 className="report-title">{getReportTitle(report)}</h4>
              <div className="total-score">
                <span className="score-label">总分</span>
                <span className="score-value">{formatScore(report.weighted_total)}</span>
              </div>
            </div>
            <StudentSummary report={report} />
            <SimpleScoreCard dimensions={report.dimensions} />
            {report.expert_conclusion ? (
              <div className="expert-comment">
                <h5>专家评语</h5>
                <p>{report.expert_conclusion}</p>
              </div>
            ) : null}
            <button
              type="button"
              className="download-btn"
              onClick={handleDownloadReport}
              disabled={downloading}
            >
              {downloading ? "下载中..." : "下载简洁报告"}
            </button>
          </div>
        ) : (
          <p className="empty-hint">{selectedPaperId ? "报告尚未生成，请稍后刷新" : "选择一篇论文查看评价结果"}</p>
        )}
      </section>
    </div>
  );
}

function DecisionButtons({
  value,
  onChange,
}: {
  value: ReviewDecision;
  onChange: (value: ReviewDecision) => void;
}) {
  return (
    <div className="decision-buttons" aria-label="专家意见标记">
      {(["agree", "reject", "neutral"] as ReviewDecision[]).map((decision) => (
        <button
          key={decision}
          type="button"
          className={value === decision ? "selected" : ""}
          onClick={() => onChange(decision)}
          title={REVIEW_DECISION_TEXT[decision]}
        >
          {REVIEW_DECISION_LABELS[decision]}
        </button>
      ))}
    </div>
  );
}

function DimensionReviewSection({
  dimension,
  decision,
  note,
  editable = false,
  onDecisionChange,
  onNoteChange,
  expertScore,
  onExpertScoreChange,
}: {
  dimension: DimensionScore;
  decision?: ReviewDecision;
  note?: string;
  editable?: boolean;
  onDecisionChange?: (dimensionKey: string, decision: ReviewDecision) => void;
  onNoteChange?: (dimensionKey: string, note: string) => void;
  expertScore?: string;
  onExpertScoreChange?: (dimensionKey: string, score: string) => void;
}) {
  const details = getModelDetails(dimension);
  const columnCount = Math.max(details.length, 1);
  const modelGridStyle = {
    gridTemplateColumns: `120px repeat(${columnCount}, minmax(160px, 1fr))`,
    minWidth: `${120 + columnCount * 160}px`,
  };
  const rows: { label: string; value: (detail: ModelDetail) => unknown }[] = [
    { label: "分数", value: (detail) => detail.score },
    { label: "小结", value: (detail) => detail.summary },
    { label: "判断", value: (detail) => detail.core_judgment },
    { label: "根因", value: (detail) => detail.score_rationale },
    { label: "证据", value: (detail) => detail.evidence_quotes },
    { label: "优点", value: (detail) => detail.strengths },
    { label: "缺点", value: (detail) => detail.weaknesses },
    { label: "风险", value: (detail) => detail.review_flags },
  ];

  return (
    <article className="review-section">
      <div className="review-section-header">
        <div>
          <h4>{dimension.name_zh}</h4>
          <small>
            mean {formatScore(dimension.ai.mean_score)} / std {formatScore(dimension.ai.std_score)} / {getConfidenceLabel(dimension)}
          </small>
        </div>
        {editable ? (
          <DecisionButtons
            value={decision ?? "neutral"}
            onChange={(nextDecision) => onDecisionChange?.(dimension.key, nextDecision)}
          />
        ) : null}
      </div>
      <div className="model-table" role="table" aria-label={`${dimension.name_zh} 评审意见`}>
        <div className="model-row model-head" role="row" style={modelGridStyle}>
          <span role="columnheader">字段</span>
          {details.map((_, index) => (
            <span key={index} role="columnheader">
              {modelLabel(index)}
            </span>
          ))}
        </div>
        {rows.map((row) => (
          <div className="model-row" role="row" key={row.label} style={modelGridStyle}>
            <strong role="cell">{row.label}</strong>
            {details.map((detail, index) => (
              <span role="cell" key={`${row.label}-${index}`}>
                {toText(row.value(detail))}
              </span>
            ))}
          </div>
        ))}
      </div>
      {editable ? (
        <div className="review-note-grid">
          <label>
            专家分数
            <input
              type="number"
              min="0"
              max="100"
              step="0.1"
              value={expertScore ?? formatScore(dimension.ai.mean_score)}
              onChange={(event) => onExpertScoreChange?.(dimension.key, event.target.value)}
            />
          </label>
          <label className="review-note">
            专家补充意见
            <textarea
              value={note ?? ""}
              placeholder="缺省为无意见；如打叉，请说明不采纳的理由。"
              onChange={(event) => onNoteChange?.(dimension.key, event.target.value)}
            />
          </label>
        </div>
      ) : null}
    </article>
  );
}

function InternalReportView({
  report,
  editable = false,
  decisions = {},
  notes = {},
  expertScores = {},
  onDecisionChange,
  onNoteChange,
  onExpertScoreChange,
}: {
  report: InternalReport;
  editable?: boolean;
  decisions?: Record<string, ReviewDecision>;
  notes?: DimensionGridState;
  expertScores?: DimensionGridState;
  onDecisionChange?: (dimensionKey: string, decision: ReviewDecision) => void;
  onNoteChange?: (dimensionKey: string, note: string) => void;
  onExpertScoreChange?: (dimensionKey: string, score: string) => void;
}) {
  return (
    <div className="report-content internal-report">
      <div className="report-header">
        <div>
          <p className="eyebrow">专家评审包</p>
          <h4 className="report-title">{getReportTitle(report)}</h4>
          <small>框架版本：{report.framework?.version ?? "V2.40"}</small>
        </div>
        <div className="total-score">
          <span className="score-label">总分</span>
          <span className="score-value">{formatScore(report.weighted_total)}</span>
        </div>
      </div>
      <div className="status-strip">
        <span>准入：{report.precheck_status ?? "未记录"}</span>
        <span>{report.expert_review_required ? "建议专家复核" : "未触发强制复核"}</span>
        <span>{report.conclusion ?? "待结论"}</span>
      </div>
      {report.dimensions.map((dimension) => (
        <DimensionReviewSection
          key={dimension.key}
          dimension={dimension}
          editable={editable}
          decision={decisions[dimension.key] ?? "neutral"}
          note={notes[dimension.key] ?? ""}
          onDecisionChange={onDecisionChange}
          onNoteChange={onNoteChange}
          expertScore={expertScores[dimension.key]}
          onExpertScoreChange={onExpertScoreChange}
        />
      ))}
    </div>
  );
}

function EditorDashboard() {
  const [queue, setQueue] = useState<ReviewQueueItem[]>([]);
  const [experts, setExperts] = useState<User[]>([]);
  const [selectedExpertId, setSelectedExpertId] = useState<string>("");
  const [selectedItem, setSelectedItem] = useState<ReviewQueueItem | null>(null);
  const [internalReport, setInternalReport] = useState<InternalReport | null>(null);
  const [message, setMessage] = useState<string>("");

  const refresh = async () => {
    const [queueItems, expertItems] = await Promise.all([getReviewQueue(), listExperts()]);
    setQueue(queueItems);
    setExperts(expertItems);
    setSelectedExpertId((current) => current || expertItems[0]?.id || "");
  };

  useEffect(() => {
    void refresh().catch(() => {
      setQueue([]);
      setExperts([]);
      setSelectedExpertId("");
    });
  }, []);

  const openInternalReport = async (item: ReviewQueueItem) => {
    try {
      setSelectedItem(item);
      setInternalReport(await getInternalReport(item.paper_id));
      setMessage("");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "内部评审包读取失败");
    }
  };

  const assignSelected = async (item: ReviewQueueItem) => {
    if (!selectedExpertId) {
      setMessage("请先选择专家");
      return;
    }
    try {
      await assignExpert(item.task_id, [selectedExpertId]);
      setMessage("复核任务已分配");
      await refresh();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "复核任务分配失败");
    }
  };

  return (
    <div className="dashboard-grid professional-view">
      <section className="panel queue-section">
        <p className="eyebrow">编辑入口</p>
        <h2>编辑 / 专家工作台</h2>
        <label className="stack">
          复核专家
          <select value={selectedExpertId} onChange={(event) => setSelectedExpertId(event.target.value)}>
            {experts.map((expert) => (
              <option value={expert.id} key={expert.id}>
                {expert.display_name ?? expert.email}
              </option>
            ))}
          </select>
        </label>
        {message ? <p className="info-message">{message}</p> : null}
        <h3>复核队列</h3>
        <ul className="list task-list">
          {queue.length === 0 ? <li className="empty-hint">暂无复核任务</li> : null}
          {queue.map((item) => (
            <li key={item.task_id} className={selectedItem?.task_id === item.task_id ? "selected" : ""}>
              <div>
                <strong>{item.paper_title ?? item.paper_id}</strong>
                <small>低置信维度：{item.low_confidence_dimensions.join("、") || "人工复核"}</small>
              </div>
              <div className="row-actions">
                <button type="button" onClick={() => void openInternalReport(item)}>
                  查看评审包
                </button>
                <button type="button" onClick={() => void assignSelected(item)}>
                  分配
                </button>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel report-section wide-panel">
        {internalReport ? (
          <InternalReportView report={internalReport} />
        ) : (
          <p className="empty-hint">选择队列中的稿件查看 PDF 式内部评审包。</p>
        )}
      </section>
    </div>
  );
}

function ExpertDashboard() {
  const [reviews, setReviews] = useState<ReviewTask[]>([]);
  const [selectedReview, setSelectedReview] = useState<ReviewTask | null>(null);
  const [internalReport, setInternalReport] = useState<InternalReport | null>(null);
  const [decisions, setDecisions] = useState<Record<string, ReviewDecision>>({});
  const [notes, setNotes] = useState<DimensionGridState>({});
  const [expertScores, setExpertScores] = useState<DimensionGridState>({});
  const [message, setMessage] = useState<string>("");

  const refresh = async () => setReviews(await listMyReviews());

  useEffect(() => {
    void refresh().catch(() => setReviews([]));
  }, []);

  const openReview = async (review: ReviewTask) => {
    try {
      setSelectedReview(review);
      const report = await getInternalReport(review.paper_id);
      setInternalReport(report);
      setDecisions({});
      setNotes({});
      setExpertScores(
        Object.fromEntries(
          report.dimensions.map((dimension) => [dimension.key, formatScore(dimension.ai.mean_score)])
        )
      );
      setMessage("");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "评审包读取失败");
    }
  };

  const updateDecision = (dimensionKey: string, decision: ReviewDecision) => {
    setDecisions((current) => ({ ...current, [dimensionKey]: decision }));
  };

  const updateNote = (dimensionKey: string, note: string) => {
    setNotes((current) => ({ ...current, [dimensionKey]: note }));
  };

  const updateExpertScore = (dimensionKey: string, score: string) => {
    setExpertScores((current) => ({ ...current, [dimensionKey]: score }));
  };

  const buildComments = (report: InternalReport): ReviewCommentPayload[] =>
    report.dimensions.flatMap((dimension) => {
      const decision = decisions[dimension.key];
      const aiScore = dimension.ai.mean_score;
      const rawExpertScore = expertScores[dimension.key] ?? formatScore(aiScore);
      const expertScore = Number(rawExpertScore);
      const note = notes[dimension.key]?.trim();
      const scoreChanged = Number.isFinite(expertScore) && Math.abs(expertScore - aiScore) > 0.05;
      if (!decision && !note && !scoreChanged) {
        return [];
      }
      return [
        {
          dimension_key: dimension.key,
          ai_score: aiScore,
          expert_score: Number.isFinite(expertScore) ? expertScore : aiScore,
          reason: note || `${REVIEW_DECISION_LABELS[decision ?? "neutral"]} ${REVIEW_DECISION_TEXT[decision ?? "neutral"]}`,
        },
      ];
    });

  const submitCurrentReview = async () => {
    if (!selectedReview || !internalReport) return;
    const comments = buildComments(internalReport);
    if (comments.length === 0) {
      setMessage("请至少对一个维度打勾、打叉、调整分数或填写意见后再提交");
      return;
    }
    try {
      await submitReview(selectedReview.review_id, comments);
      setMessage("专家复核意见已提交");
      await refresh();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "专家复核意见提交失败");
    }
  };

  return (
    <div className="dashboard-grid professional-view">
      <section className="panel queue-section">
        <p className="eyebrow">专家入口</p>
        <h2>编辑 / 专家工作台</h2>
        <h3>我的复核任务</h3>
        <ul className="list task-list">
          {reviews.length === 0 ? <li className="empty-hint">暂无复核任务</li> : null}
          {reviews.map((review) => (
            <li key={review.review_id} className={selectedReview?.review_id === review.review_id ? "selected" : ""}>
              <div>
                <strong>{review.paper_title ?? review.task_id}</strong>
                <small>{getStatusLabel(review.status)}</small>
              </div>
              <button type="button" onClick={() => void openReview(review)}>
                打开评审包
              </button>
            </li>
          ))}
        </ul>
        {internalReport ? (
          <button type="button" className="download-btn" onClick={() => void submitCurrentReview()}>
            提交复核意见
          </button>
        ) : null}
        {message ? <p className="info-message">{message}</p> : null}
      </section>

      <section className="panel report-section wide-panel">
        {internalReport ? (
          <InternalReportView
            report={internalReport}
            editable
            decisions={decisions}
            notes={notes}
            expertScores={expertScores}
            onDecisionChange={updateDecision}
            onNoteChange={updateNote}
            onExpertScoreChange={updateExpertScore}
          />
        ) : (
          <p className="empty-hint">选择一项复核任务后，可对每个维度打勾、打叉或保留无意见。</p>
        )}
      </section>
    </div>
  );
}

function AdminDashboard() {
  const [users, setUsers] = useState<User[]>([]);
  const [inviteEmail, setInviteEmail] = useState("new-user@example.com");
  const [inviteRole, setInviteRole] = useState("submitter");

  const refresh = async () => setUsers(await listUsers());

  useEffect(() => {
    void refresh().catch(() => setUsers([]));
  }, []);

  return (
    <div className="dashboard-grid">
      <section className="panel">
        <p className="eyebrow">管理员入口</p>
        <h2>系统管理</h2>
        <form
          className="stack"
          onSubmit={async (event) => {
            event.preventDefault();
            await createInvitation(inviteEmail, inviteRole);
            await refresh();
          }}
        >
          <input value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} />
          <select value={inviteRole} onChange={(event) => setInviteRole(event.target.value)}>
            <option value="submitter">投稿人</option>
            <option value="editor">编辑</option>
            <option value="expert">专家</option>
            <option value="admin">管理员</option>
          </select>
          <button type="submit">创建邀请</button>
        </form>
      </section>

      <section className="panel">
        <h3>用户目录</h3>
        <ul className="list">
          {users.map((user) => (
            <li key={user.id}>
              {user.display_name ?? user.email} - {user.role}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function RoleDashboard({ user }: { user: User }) {
  return (
    <>
      <PortalIntro user={user} />
      {user.role === "submitter" ? <SubmitterDashboard /> : null}
      {user.role === "editor" ? <EditorDashboard /> : null}
      {user.role === "expert" ? <ExpertDashboard /> : null}
      {user.role === "admin" ? <AdminDashboard /> : null}
    </>
  );
}

export function App({ initialUser }: AppProps) {
  const [user, setUser] = useState<User | null | undefined>(initialUser);

  useEffect(() => {
    if (initialUser !== undefined) {
      return;
    }
    void getCurrentUser()
      .then((currentUser) => setUser(currentUser))
      .catch(() => setUser(null));
  }, [initialUser]);

  if (user === undefined) {
    return (
      <div className="shell">
        <p>正在加载会话...</p>
      </div>
    );
  }

  if (user === null) {
    return (
      <div className="shell">
        <LoginForm onLoggedIn={setUser} />
      </div>
    );
  }

  return (
    <div className="shell">
      <header className="app-header">
        <div>
          <h1>SocialEval</h1>
          <p>{user.display_name ?? user.email}</p>
        </div>
        <button
          type="button"
          onClick={async () => {
            await logout();
            setUser(null);
          }}
        >
          退出登录
        </button>
      </header>
      <RoleDashboard user={user} />
    </div>
  );
}
