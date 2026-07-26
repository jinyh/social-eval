export type User = {
  id: string;
  email: string;
  role: "submitter" | "editor" | "expert" | "admin";
  display_name?: string | null;
  is_active?: boolean;
  created_at?: string;
  last_login_at?: string | null;
  password_changed_at?: string | null;
  password_reset_required?: boolean;
  mfa_enabled?: boolean;
};

export type LoginChallenge = {
  status: "mfa_required" | "mfa_setup_required";
  user: null;
};

export type MfaSetup = {
  secret: string;
  provisioning_uri: string;
  qr_svg: string;
};

export type ApiKeyMetadata = {
  id: string;
  name?: string | null;
  key_prefix: string;
  is_active: boolean;
  created_at: string;
  last_used_at?: string | null;
  expires_at: string;
};

export type CreatedApiKey = ApiKeyMetadata & {
  api_key: string;
};

export type Invitation = {
  id: string;
  email: string;
  role: User["role"];
  status: "pending" | "used" | "expired" | "revoked";
  email_status: string;
  created_at: string;
  expires_at: string;
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
  progress: TaskProgress;
};

export type TaskProgress = {
  stage: string;
  stage_label: string;
  completed: number;
  total: number;
  percent: number;
  current_dimension?: string | null;
  current_model_slot?: number | null;
  heartbeat_at?: string | null;
  is_stalled: boolean;
  failure_detail?: string | null;
  review_protocol_version?: string | null;
};

export type NotificationItem = {
  id: string;
  event_type: string;
  object_type: string;
  object_id: string;
  payload?: Record<string, unknown> | null;
  read_at?: string | null;
  created_at: string;
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
  review_stage: "blind" | "comparison" | "completed";
  required_dimensions: string[];
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
  model_results?: Array<{
    model_label: string;
    score: number;
    evidence_quotes?: string[] | string;
    analysis?: string | null;
  }>;
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
  statement_decisions?: Record<string, ExpertDecisionState> | null;
  comparison_reason?: string | null;
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
  weighted_total?: number | null;
  review_stage?: "blind" | "comparison" | "completed";
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
  expert_score: number;
  reason: string;
  statement_decisions?: Record<string, ExpertDecisionState>;
};

export type ExpertComparisonInput = {
  dimension_key: string;
  statement_decisions: Record<string, ExpertDecisionState>;
  comparison_reason: string;
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

export type PreReviewDecision =
  | "decline_without_review"
  | "revise_resubmit"
  | "send_external_review"
  | "priority_external_review";

export type FinalDecision =
  | "reject"
  | "major_revision"
  | "minor_accept"
  | "direct_accept";

export type EditorialDecision = PreReviewDecision | FinalDecision;

export type EditorialUnit = {
  id: string;
  journal_id: string;
  journal_name: string;
  code: string;
  name: string;
  policy_key: string;
  policy_version: string;
  rollout_state: "shadow" | "active";
};

export type ModelSet = {
  name: string;
  status: string;
  provider_names: string[];
  review_protocol: string;
  review_mode: "opposite_groups" | "all_peers";
  model_groups?: {
    lenient: string[];
    strict: string[];
  };
};

export type ValidationRun = {
  id: string;
  unit_id?: string | null;
  validation_type: "calibration" | "holdout" | "final_validation" | "model_upgrade";
  framework_version: string;
  model_set_version: string;
  sample_manifest_sha256: string;
  sample_count: number;
  metrics: Record<string, unknown>;
  status: "draft" | "signed";
  signed_by?: string | null;
  signed_at?: string | null;
  created_at: string;
};

export type EditorialSubmissionListItem = {
  id: string;
  unit_id: string;
  external_manuscript_id?: string | null;
  title?: string | null;
  status: string;
  responsible_editor_id?: string | null;
  recommendation_state: "shadow" | "ready" | "withheld";
  current_report_version: number;
  created_at: string;
  updated_at: string;
};

export type AnonymousManuscriptBlock = {
  type: "heading" | "paragraph" | "table" | "footnote" | "page_break";
  text?: string | null;
  level?: number | null;
  rows?: string[][] | null;
  number?: string | number | null;
  page?: number | null;
};

export type AnonymousManuscript = {
  manuscript_id: string;
  document_version: number;
  blocks: AnonymousManuscriptBlock[];
  risk_flags: string[];
  omitted_content_types: string[];
  notice: string;
};

export type EditorialSubmissionStatusGroup =
  | "processing"
  | "awaiting_action"
  | "completed"
  | "failed";

export type EditorialSubmissionListQuery = {
  unitId?: string;
  keyword?: string;
  statusGroup?: EditorialSubmissionStatusGroup;
  submittedFrom?: string;
  submittedTo?: string;
  page?: number;
  pageSize?: number;
};

export type EditorialSubmissionPage = {
  items: EditorialSubmissionListItem[];
  total: number;
  page: number;
  page_size: number;
  status_counts: Record<EditorialSubmissionStatusGroup, number>;
};

export type EditorialOpinion = {
  id: string;
  opinion_type: "ai_independent" | "ai_synthesis" | "editor_final";
  version: number;
  sequence: number;
  content: Record<string, unknown>;
  model_name?: string | null;
  created_by?: string | null;
  is_locked: boolean;
  created_at: string;
};

export type EditorialDecisionRecord = {
  id: string;
  version: number;
  decision_stage: "legacy" | "pre_review" | "final";
  suggested_decision?: EditorialDecision | null;
  final_decision: EditorialDecision;
  recommendation_state: "shadow" | "ready" | "withheld";
  rationale?: string | null;
  bypassed_expert_gate: boolean;
  actor_id: string;
  is_locked: boolean;
  created_at: string;
};

export type EditorialDimensionScore = {
  dimension_key: string;
  model_name?: string | null;
  score: number;
  band?: string | null;
  evidence_quotes?: unknown;
};

export type EditorialModelResult = {
  model_label: string;
  score: number;
  band: string;
  band_label: string;
  evidence_quotes: unknown;
  analysis: string;
};

export type EditorialDimensionSummary = {
  dimension_key: string;
  dimension_name: string;
  mean_score: number;
  std_score: number;
  confidence_label: string;
  band: string;
  band_label: string;
  difference_level: "consensus" | "band_difference" | "expert_review";
  difference_label: string;
  requires_expert_review: boolean;
  model_results: EditorialModelResult[];
};

export type CcbSummary = {
  label: string;
  base_score: number;
  bonus_score: number;
  ceiling_score?: number | null;
  ceiling_label: string;
  final_score: number;
  notice: string;
};

export type PositionAxisSummary = {
  axis_key: string;
  axis_name: string;
  focus_label: string;
  guiding_question: string;
  score: number;
  score_range: number[];
  evidence_quotes: string[];
  has_model_difference: boolean;
};

export type PositionSummary = {
  total_score: number;
  strength_label: string;
  confidence_label: string;
  agreement_label: string;
  review_required: boolean;
  conflict_with_precheck: boolean;
  conflict_message?: string | null;
  axes: PositionAxisSummary[];
  notice: string;
};

export type EditorialSubmissionDetail = EditorialSubmissionListItem & {
  paper_id: string;
  task_id: string;
  anonymization_status: string;
  anonymization_result?: Record<string, unknown> | null;
  formal_check_status?: string | null;
  formal_check_result?: Record<string, unknown> | null;
  precheck_status?: string | null;
  precheck_result?: Record<string, unknown> | null;
  fit_status?: string | null;
  fit_result?: Record<string, unknown> | null;
  internal_candidate_decision?: EditorialDecision | null;
  manual_review_requested: boolean;
  six_dimension: EditorialDimensionScore[];
  six_dimension_summary: {
    model_participation: { count: number; labels: string[] };
    difference_count: number;
    expert_review_dimension_count: number;
    dimensions: EditorialDimensionSummary[];
  };
  ccb_summary?: CcbSummary | null;
  position_summary?: PositionSummary | null;
  position_assessment?: Record<string, unknown> | null;
  model_set_version: string;
  review_protocol_version: string;
  review_protocol_label: string;
  progress: TaskProgress;
  documents: Record<string, string>;
  expert_reviews: Array<{
    review_id: string;
    status: string;
    blind_submitted_at?: string | null;
    ai_revealed_at?: string | null;
    completed_at?: string | null;
    comments: Array<{
      dimension_key: string;
      expert_score: number;
      reason: string;
      statement_decisions?: Record<string, string> | null;
      comparison_reason?: string | null;
    }>;
  }>;
  opinions: EditorialOpinion[];
  decisions: EditorialDecisionRecord[];
};
