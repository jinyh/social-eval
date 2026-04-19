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
  low_confidence_dimensions: string[];
};

export type ReviewTask = {
  review_id: string;
  task_id: string;
  status: string;
};

export type UserListResponse = {
  items: User[];
};

export type DimensionScore = {
  name_zh: string;
  name_en?: string;
  ai: {
    mean_score: number;
  };
  summary?: string | null;
};

export type PublicReport = {
  title?: string | null;
  weighted_total: number;
  conclusion?: string | null;
  dimensions: DimensionScore[];
  expert_conclusion?: string | null;
};
