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
  task_status: string;
  low_confidence_dimensions: string[];
};

export type ReviewTask = {
  review_id: string;
  task_id: string;
  paper_id: string;
  paper_title?: string | null;
  status: string;
};

export type UserListResponse = {
  items: User[];
};

export type DimensionScore = {
  key: string;
  name_zh: string;
  name_en?: string;
  weight?: number;
  ai: {
    mean_score: number;
    std_score?: number;
    is_high_confidence?: boolean;
    model_scores?: Record<string, number>;
    model_details?: ModelDetail[];
  };
  summary?: string | null;
};

export type FrameworkInfo = {
  name: string;
  version: string;
  path?: string;
};

export type ModelDetail = {
  model_name: string;
  score: number;
  summary?: string | null;
  core_judgment?: string | null;
  score_rationale?: string | null;
  strengths?: string[];
  weaknesses?: string[];
  limit_rule_triggered?: unknown[];
  boundary_note?: string | null;
  review_flags?: string[];
  evidence_quotes?: string[];
};

export type ExpertReviewSummary = {
  review_id: string;
  status: string;
  comments: {
    dimension_key: string;
    expert_score: number;
    reason: string;
  }[];
};

export type PublicReport = {
  report_type?: "public";
  paper_id?: string;
  task_id?: string;
  title?: string | null;
  paper_title?: string | null;
  framework?: FrameworkInfo | null;
  model_count?: number;
  ai_weighted_total?: number | null;
  expert_adjusted_total?: number | null;
  weighted_total: number;
  conclusion?: string | null;
  expert_review_required?: boolean;
  dimensions: DimensionScore[];
  expert_reviews?: ExpertReviewSummary[];
  expert_conclusion?: string | null;
};

export type InternalReport = Omit<PublicReport, "report_type" | "expert_reviews"> & {
  report_type?: "internal";
  models?: string[];
  precheck_status?: string | null;
  precheck_result?: Record<string, unknown> | null;
  expert_reviews?: (ExpertReviewSummary & {
    expert_id?: string;
    version?: number;
    completed_at?: string | null;
    comments: (ExpertReviewSummary["comments"][number] & { ai_score: number })[];
  })[];
};

export type ReviewCommentPayload = {
  dimension_key: string;
  ai_score: number;
  expert_score: number;
  reason: string;
};
