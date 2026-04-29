import type {
  DimensionMetric,
  DimensionScore,
  ExpertDecisionState,
  InternalDimensionScore,
  InternalReport,
  ModelScoreMap,
  PublicReport,
  ReviewCommentInput,
} from "./types";

export const STANDARD_DIMENSIONS: DimensionMetric[] = [
  { key: "problem_originality", name: "问题创新性", nameEn: "Problem Originality", score: 70 },
  { key: "literature_insight", name: "现状洞察度", nameEn: "Literature Insight", score: 70 },
  { key: "analytical_framework", name: "分析框架建构力", nameEn: "Analytical Framework", score: 70 },
  { key: "logical_coherence", name: "逻辑严密性", nameEn: "Logical Coherence", score: 70 },
  { key: "conclusion_consensus", name: "结论可接受性", nameEn: "Conclusion Acceptability", score: 70 },
  { key: "forward_extension", name: "前瞻延展性", nameEn: "Forward Extension", score: 70 },
];

const MODEL_DISPLAY_ORDER = [
  { label: "模型一", aliases: ["gpt-5.4", "openai/gpt-5.4"] },
  { label: "模型二", aliases: ["glm-5.1", "z-ai/glm-5.1"] },
  { label: "模型三", aliases: ["qwen3.6-plus", "qwen/qwen3.6-plus", "qwen 3.6 plus"] },
];

export type AnonymousModelScore = {
  label: string;
  score: number | null;
};

export type ReviewOpinion = {
  id: string;
  dimensionKey: string;
  title: string;
  body: string;
  evidence?: string;
};

export function safeNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

export function formatScore(value: number | undefined | null): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "--";
  return value.toFixed(1);
}

export function getReportTitle(report: PublicReport | InternalReport | null | undefined): string {
  if (!report) return "未命名论文";
  return report.title ?? report.paper_title ?? "未命名论文";
}

export function normalizePublicDimensions(report: PublicReport | null | undefined): DimensionMetric[] {
  if (!report?.dimensions?.length) return [];
  return report.dimensions.map((dimension, index) => normalizePublicDimension(dimension, index));
}

export function normalizeInternalDimensions(report: InternalReport | null | undefined): DimensionMetric[] {
  if (!report?.dimensions?.length) return [];
  return report.dimensions.map((dimension, index) => normalizeInternalDimension(dimension, index));
}

export function normalizePublicDimension(dimension: DimensionScore, index: number): DimensionMetric {
  const fallback = STANDARD_DIMENSIONS[index];
  const score = safeNumber(dimension.ai?.mean_score, fallback?.score ?? 0);
  return {
    key: dimension.key ?? fallback?.key ?? `dimension-${index + 1}`,
    name: dimension.name_zh || fallback?.name || `维度 ${index + 1}`,
    nameEn: dimension.name_en ?? fallback?.nameEn,
    score,
    summary: dimension.summary ?? dimension.analysis,
    stdScore: dimension.ai?.std_score,
    confidence: confidenceLabel(dimension.ai?.is_high_confidence, dimension.ai?.std_score),
    weight: dimension.weight,
  };
}

export function normalizeInternalDimension(dimension: InternalDimensionScore, index: number): DimensionMetric {
  const fallback = STANDARD_DIMENSIONS[index];
  const score = safeNumber(dimension.ai?.mean_score, fallback?.score ?? 0);
  return {
    key: dimension.key ?? fallback?.key ?? `dimension-${index + 1}`,
    name: dimension.name_zh ?? dimension.name_en ?? fallback?.name ?? `维度 ${index + 1}`,
    nameEn: dimension.name_en ?? fallback?.nameEn,
    score,
    summary: dimension.summary ?? dimension.analysis,
    stdScore: dimension.ai?.std_score,
    confidence: confidenceLabel(dimension.ai?.is_high_confidence, dimension.ai?.std_score, dimension.ai?.confidence),
    weight: dimension.weight,
  };
}

export function confidenceLabel(
  isHighConfidence?: boolean,
  stdScore?: number,
  explicitConfidence?: string | number | null
): string {
  if (typeof explicitConfidence === "string" && explicitConfidence.trim()) return explicitConfidence;
  if (typeof explicitConfidence === "number") return explicitConfidence >= 0.8 ? "高置信度" : "需复核";
  if (typeof isHighConfidence === "boolean") return isHighConfidence ? "高置信度" : "需复核";
  if (typeof stdScore !== "number") return "待确认";
  if (stdScore <= 5) return "高置信度";
  if (stdScore <= 8) return "中等置信度";
  return "需复核";
}

export function anonymizeModelScores(modelScores: ModelScoreMap | undefined): AnonymousModelScore[] {
  if (!modelScores) {
    return MODEL_DISPLAY_ORDER.map((model) => ({ label: model.label, score: null }));
  }

  const normalizedEntries = Object.entries(modelScores);
  const usedKeys = new Set<string>();
  const ordered = MODEL_DISPLAY_ORDER.map((model) => {
    const match = normalizedEntries.find(([key]) =>
      model.aliases.some((alias) => normalizeModelKey(key).includes(normalizeModelKey(alias)))
    );
    if (match) usedKeys.add(match[0]);
    return { label: model.label, score: match ? extractModelScore(match[1]) : null };
  });

  const unknownScores = normalizedEntries.filter(([key]) => !usedKeys.has(key));
  unknownScores.slice(0, MODEL_DISPLAY_ORDER.length).forEach(([, value], index) => {
    if (ordered[index].score === null) {
      ordered[index] = { ...ordered[index], score: extractModelScore(value) };
    }
  });

  return ordered;
}

export function buildReviewOpinions(dimension: InternalDimensionScore, index: number): ReviewOpinion[] {
  const metric = normalizeInternalDimension(dimension, index);
  const analysisItems = normalizeTextList(dimension.ai?.analysis ?? dimension.analysis);
  const evidenceItems = normalizeTextList(dimension.ai?.evidence_quotes);
  const riskItems = normalizeTextList(dimension.risk_flags);
  const triggerItems = normalizeTextList(dimension.trigger_reasons);
  const bodies = [...analysisItems, ...riskItems, ...triggerItems];
  const fallbackBody = metric.summary || "暂无可展示的模型分析，专家可直接基于论文材料给出补充意见。";
  const source = bodies.length > 0 ? bodies : [fallbackBody];

  return source.map((body, itemIndex) => ({
    id: `${metric.key}-${itemIndex}`,
    dimensionKey: metric.key,
    title: `${metric.name}意见 ${itemIndex + 1}`,
    body,
    evidence: evidenceItems[itemIndex] ?? evidenceItems[0],
  }));
}

export function buildStudentSummary(report: PublicReport): {
  overall: string;
  strengths: string[];
  priorities: string[];
  expertText: string;
} {
  const dimensions = normalizePublicDimensions(report);
  const sorted = [...dimensions].sort((a, b) => b.score - a.score);
  const strengths = sorted
    .slice(0, 2)
    .map((dimension) => `${dimension.name}（${formatScore(dimension.score)}分）：${dimension.summary || "表现相对稳定。"}`);
  const priorities = sorted
    .slice(-2)
    .reverse()
    .map((dimension) => `${dimension.name}（${formatScore(dimension.score)}分）：${dimension.summary || "建议补充论证与材料。"}`);
  const expertText =
    report.expert_conclusion ??
    report.expert_reviews?.flatMap((review) => review.comments.map((comment) => comment.reason)).join("\n") ??
    "暂无专家/编辑补充意见。";
  return {
    overall: report.conclusion ?? "当前报告尚未生成明确综合结论，请等待评价流程完成。",
    strengths,
    priorities,
    expertText,
  };
}

export function buildSubmitComments(
  metrics: DimensionMetric[],
  decisionsByOpinion: Record<string, ExpertDecisionState>,
  opinionsByDimension: Record<string, ReviewOpinion[]>,
  scoreDrafts: Record<string, number>,
  reasonDrafts: Record<string, string>
): { comments: ReviewCommentInput[]; missingRejectedReasons: string[] } {
  const missingRejectedReasons: string[] = [];
  const comments = metrics.map((metric) => {
    const opinions = opinionsByDimension[metric.key] ?? [];
    const states = opinions.map((opinion) => decisionsByOpinion[opinion.id] ?? "neutral");
    const hasReject = states.includes("reject");
    const hasAccept = states.includes("accept");
    const score = clampScore(safeNumber(scoreDrafts[metric.key], metric.score));
    const manualReason = reasonDrafts[metric.key]?.trim() ?? "";
    if (hasReject && !manualReason) missingRejectedReasons.push(metric.name);

    let reason = manualReason;
    if (!reason && hasReject) reason = "不认可该维度部分 AI 判断，需专家修正。";
    if (!reason && hasAccept) reason = "认可 AI 对该维度的判断。";
    if (!reason) reason = "无补充意见。";

    return {
      dimension_key: metric.key,
      ai_score: clampScore(metric.score),
      expert_score: score,
      reason,
    };
  });
  return { comments, missingRejectedReasons };
}

export function clampScore(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(100, Math.max(0, value));
}

export function normalizeTextList(value: unknown): string[] {
  if (!value) return [];
  if (typeof value === "string") return value.trim() ? [value] : [];
  if (!Array.isArray(value)) return [];
  return value
    .flatMap((item) => {
      if (typeof item === "string") return item;
      if (Array.isArray(item)) return item.filter((nested): nested is string => typeof nested === "string");
      return [];
    })
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeModelKey(value: string): string {
  return value.toLowerCase().replaceAll("_", "-").replaceAll(" ", "");
}

function extractModelScore(value: ModelScoreMap[string]): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (value && typeof value === "object") {
    if (typeof value.score === "number" && Number.isFinite(value.score)) return value.score;
    if (typeof value.mean_score === "number" && Number.isFinite(value.mean_score)) return value.mean_score;
  }
  return null;
}
