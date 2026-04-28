export type User = {
  id: string;
  email: string;
  role: "submitter" | "editor" | "expert" | "admin";
  display_name?: string | null;
};

export type PaperListItem = {
  paper_id: string;
  title?: string | null;
  original_filename: string;
  paper_status: string;
  precheck_status?: string | null;
};

export type PaperStatus = {
  paper_id: string;
  task_id: string;
  paper_status: string;
  task_status: string;
  precheck_status?: string | null;
  reliability_summary?: {
    total_dimensions: number;
    high_confidence_count: number;
    low_confidence_count: number;
    overall_high_confidence: boolean;
  } | null;
};

export type ReviewQueueItem = {
  task_id: string;
  paper_id: string;
  paper_title?: string | null;
  paper_status?: string | null;
  task_status?: string;
  low_confidence_dimensions: string[];
};

export type ReviewTask = {
  review_id: string;
  task_id: string;
  status: string;
  paper_id?: string | null;
  paper_title?: string | null;
};

export type UserListResponse = {
  items: User[];
};

export type DimensionScore = {
  key?: string;
  name_zh: string;
  name_en?: string;
  weight?: number;
  ai: {
    mean_score: number;
    std_score?: number;
    is_high_confidence?: boolean;
  };
  summary?: string | null;
  analysis?: string | null;
};

export type PublicReport = {
  report_type?: "public";
  paper_id?: string;
  task_id?: string;
  title?: string | null;
  paper_title?: string | null;
  weighted_total: number;
  conclusion?: string | null;
  dimensions: DimensionScore[];
  expert_conclusion?: string | null;
  expert_reviews?: PublicExpertReview[];
};

export type ModelScoreMap = Record<string, number | { score?: number; mean_score?: number } | null | undefined>;

export type InternalAiPayload = {
  mean_score?: number;
  std_score?: number;
  is_high_confidence?: boolean;
  confidence?: string | number | null;
  model_scores?: ModelScoreMap;
  evidence_quotes?: Array<string | string[]>;
  analysis?: string[] | string | null;
};

export type InternalDimensionScore = {
  key?: string;
  name_zh?: string | null;
  name_en?: string | null;
  weight?: number;
  ai?: InternalAiPayload;
  summary?: string | null;
  analysis?: string | null;
  risk_flags?: string[];
  trigger_reasons?: string[];
};

export type InternalExpertComment = {
  dimension_key: string;
  ai_score: number;
  expert_score: number;
  reason: string;
};

export type InternalExpertReview = {
  review_id: string;
  expert_id?: string | null;
  status: string;
  version?: number;
  completed_at?: string | null;
  comments: InternalExpertComment[];
};

export type PublicExpertReview = {
  review_id: string;
  status: string;
  comments: Array<Pick<InternalExpertComment, "dimension_key" | "expert_score" | "reason">>;
};

export type InternalReport = {
  report_type?: "internal";
  paper_id?: string;
  task_id?: string;
  paper_title?: string | null;
  title?: string | null;
  precheck_status?: string | null;
  precheck_result?: Record<string, unknown> | string | null;
  weighted_total?: number;
  dimensions?: InternalDimensionScore[];
  expert_reviews?: InternalExpertReview[];
  radar_chart?: {
    labels?: string[];
    values?: number[];
    image_base64?: string;
  };
};

export type ReviewCommentInput = {
  dimension_key: string;
  ai_score: number;
  expert_score: number;
  reason: string;
};

export type ExpertDecisionState = "accept" | "reject" | "neutral";

export type DimensionMetric = {
  key: string;
  name: string;
  nameEn?: string;
  score: number;
  summary?: string | null;
  stdScore?: number;
  confidence?: string;
  weight?: number;
};
