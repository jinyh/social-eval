import type {
  ApiKeyMetadata,
  AnonymousManuscript,
  CreatedApiKey,
  InternalReport,
  ModelSet,
  NotificationItem,
  EditorialDecision,
  EditorialDecisionRecord,
  EditorialSubmissionDetail,
  EditorialSubmissionListQuery,
  EditorialSubmissionPage,
  EditorialUnit,
  Invitation,
  LoginChallenge,
  MfaSetup,
  PaperListItem,
  PaperStatus,
  PublicReport,
  ReviewCommentInput,
  ExpertComparisonInput,
  ReviewQueueItem,
  ReviewTask,
  User,
  UserListResponse,
  ValidationRun,
} from "./types";
import {
  getMockRole,
  isMockMode,
  mockExperts,
  mockEditorialSubmissionDetail,
  mockEditorialSubmissions,
  mockEditorialUnits,
  mockInternalReport,
  mockPaperStatus,
  mockPapers,
  mockPublicReport,
  mockReviewQueue,
  mockReviewTasks,
  mockUserDirectory,
  mockUsers,
} from "./mockData";

// 生产环境使用空字符串（通过 nginx 代理），开发环境使用 localhost
const API_BASE = import.meta.env.VITE_API_BASE ?? "";

async function readErrorMessage(response: Response): Promise<string> {
  const text = await response.text();
  if (text) {
    try {
      const payload = JSON.parse(text) as { detail?: unknown };
      if (typeof payload.detail === "string") return payload.detail;
      if (Array.isArray(payload.detail)) {
        return payload.detail
          .map((item) =>
            typeof item === "object" && item && "msg" in item
              ? String(item.msg)
              : String(item)
          )
          .join("；");
      }
    } catch {
      return text;
    }
    return text;
  }
  return `请求失败，状态码 ${response.status}`;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export async function getCurrentUser(): Promise<User> {
  const mockRole = getMockRole();
  if (mockRole) return mockUsers[mockRole];
  return apiFetch<User>("/api/auth/me");
}

export async function login(
  email: string,
  password: string
): Promise<User | LoginChallenge> {
  if (isMockMode()) return mockUsers.submitter;
  return apiFetch<User | LoginChallenge>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function requestPasswordReset(email: string): Promise<void> {
  await apiFetch("/api/auth/password-reset/request", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function confirmPasswordReset(
  token: string,
  newPassword: string
): Promise<void> {
  await apiFetch("/api/auth/password-reset/confirm", {
    method: "POST",
    body: JSON.stringify({ token, new_password: newPassword }),
  });
}

export async function acceptInvitation(
  token: string,
  displayName: string,
  password: string
): Promise<User> {
  return apiFetch<User>("/api/auth/invitations/accept", {
    method: "POST",
    body: JSON.stringify({
      token,
      display_name: displayName,
      password,
    }),
  });
}

export async function setupMfa(): Promise<MfaSetup> {
  return apiFetch<MfaSetup>("/api/auth/mfa/setup", { method: "POST" });
}

export async function confirmMfa(
  code: string
): Promise<{ user: User; recovery_codes: string[] }> {
  return apiFetch<{ user: User; recovery_codes: string[] }>(
    "/api/auth/mfa/confirm",
    { method: "POST", body: JSON.stringify({ code }) }
  );
}

export async function verifyMfa(code: string): Promise<User> {
  return apiFetch<User>("/api/auth/mfa/verify", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

export async function changePassword(
  currentPassword: string,
  newPassword: string,
  revokeApiKeys: boolean
): Promise<User> {
  const mockRole = getMockRole();
  if (mockRole) return mockUsers[mockRole];
  return apiFetch<User>("/api/auth/password/change", {
    method: "POST",
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
      revoke_api_keys: revokeApiKeys,
    }),
  });
}

export async function listApiKeys(): Promise<ApiKeyMetadata[]> {
  if (isMockMode()) return [];
  return apiFetch<ApiKeyMetadata[]>("/api/auth/api-keys");
}

export async function createApiKey(
  name: string,
  expiresInDays: number
): Promise<CreatedApiKey> {
  if (isMockMode()) {
    const now = new Date();
    const expiresAt = new Date(now);
    expiresAt.setDate(expiresAt.getDate() + expiresInDays);
    return {
      id: "mock-api-key",
      name,
      key_prefix: "sk_socialeval_mock",
      api_key: "sk_socialeval_mock_only",
      is_active: true,
      created_at: now.toISOString(),
      expires_at: expiresAt.toISOString(),
    };
  }
  return apiFetch<CreatedApiKey>("/api/auth/api-keys", {
    method: "POST",
    body: JSON.stringify({ name, expires_in_days: expiresInDays }),
  });
}

export async function revokeApiKey(apiKeyId: string): Promise<void> {
  if (isMockMode()) return;
  await apiFetch(`/api/auth/api-keys/${apiKeyId}`, { method: "DELETE" });
}

export async function regenerateMfaRecoveryCodes(
  password: string,
  code: string
): Promise<string[]> {
  if (isMockMode()) {
    return Array.from(
      { length: 10 },
      (_, index) => `DEMO-${String(index + 1).padStart(2, "0")}-CODE`
    );
  }
  const result = await apiFetch<{ recovery_codes: string[] }>(
    "/api/auth/mfa/recovery-codes/regenerate",
    {
      method: "POST",
      body: JSON.stringify({ password, code }),
    }
  );
  return result.recovery_codes;
}

export async function logout(): Promise<void> {
  if (isMockMode()) return;
  await apiFetch<void>("/api/auth/logout", { method: "POST" });
}

export async function listPapers(): Promise<PaperListItem[]> {
  if (isMockMode()) return mockPapers;
  const result = await apiFetch<{ items: PaperListItem[] }>("/api/papers");
  return result.items;
}

export async function deletePaper(paperId: string): Promise<void> {
  if (isMockMode()) return;
  await apiFetch<void>(`/api/papers/${paperId}`, { method: "DELETE" });
}

export async function uploadPaper(file: File): Promise<{ paper_id: string; task_id: string }> {
  if (isMockMode()) return { paper_id: "paper-mock-uploaded", task_id: "task-mock-uploaded" };
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_BASE}/api/papers`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }
  return response.json() as Promise<{ paper_id: string; task_id: string }>;
}

export async function getPaperStatus(paperId: string): Promise<PaperStatus> {
  if (isMockMode()) return { ...mockPaperStatus, paper_id: paperId };
  return apiFetch<PaperStatus>(`/api/papers/${paperId}/status`);
}

export async function getPublicReport(paperId: string): Promise<PublicReport> {
  if (isMockMode()) return { ...mockPublicReport, paper_id: paperId };
  return apiFetch<PublicReport>(`/api/papers/${paperId}/report`);
}

export async function getInternalReport(paperId: string, taskId?: string): Promise<InternalReport> {
  if (isMockMode()) return { ...mockInternalReport, paper_id: paperId };
  const query = taskId ? `?task_id=${encodeURIComponent(taskId)}` : "";
  return apiFetch<InternalReport>(`/api/papers/${paperId}/internal-report${query}`);
}

export async function getReviewQueue(): Promise<ReviewQueueItem[]> {
  if (isMockMode()) return mockReviewQueue;
  const result = await apiFetch<{ items: ReviewQueueItem[] }>("/api/reviews/queue");
  return result.items;
}

export async function listExperts(): Promise<User[]> {
  if (isMockMode()) return mockExperts;
  const result = await apiFetch<UserListResponse>("/api/users/experts");
  return result.items;
}

export async function assignExpert(taskId: string, expertIds: string[]): Promise<void> {
  if (isMockMode()) return;
  await apiFetch(`/api/reviews/${taskId}/assign`, {
    method: "POST",
    body: JSON.stringify({ expert_ids: expertIds }),
  });
}

export async function listMyReviews(): Promise<ReviewTask[]> {
  if (isMockMode()) return mockReviewTasks;
  const result = await apiFetch<{ items: ReviewTask[] }>("/api/reviews/mine");
  return result.items;
}

export async function submitBlindReview(
  reviewId: string,
  comments: ReviewCommentInput[]
): Promise<void> {
  if (isMockMode()) return;
  await apiFetch(`/api/reviews/${reviewId}/blind-submit`, {
    method: "POST",
    body: JSON.stringify({ comments }),
  });
}

export async function submitReview(
  reviewId: string,
  comparisons: ExpertComparisonInput[]
): Promise<void> {
  if (isMockMode()) return;
  await apiFetch(`/api/reviews/${reviewId}/submit`, {
    method: "POST",
    body: JSON.stringify({ comparisons }),
  });
}

export function expertDocumentUrl(reviewId: string): string {
  return `${API_BASE}/api/reviews/${reviewId}/document`;
}

export async function getExpertManuscript(
  reviewId: string
): Promise<AnonymousManuscript> {
  if (isMockMode()) {
    return {
      manuscript_id: reviewId,
      document_version: 1,
      blocks: [
        { type: "heading", level: 1, text: "匿名稿件" },
        { type: "paragraph", text: "这里展示供专家复核的匿名稿正文。" },
      ],
      risk_flags: [],
      omitted_content_types: [],
      notice: "匿名稿仅供本次评审使用，严禁转发或用于其他目的。",
    };
  }
  return apiFetch<AnonymousManuscript>(
    `/api/reviews/${reviewId}/manuscript`
  );
}

export async function listUsers(filters?: {
  q?: string;
  role?: string;
  active?: boolean;
}): Promise<User[]> {
  if (isMockMode()) return mockUserDirectory;
  const query = new URLSearchParams();
  if (filters?.q) query.set("q", filters.q);
  if (filters?.role) query.set("role", filters.role);
  if (filters?.active !== undefined) query.set("active", String(filters.active));
  const suffix = query.size ? `?${query.toString()}` : "";
  const result = await apiFetch<UserListResponse>(`/api/users${suffix}`);
  return result.items;
}

export async function createInvitation(email: string, role: string): Promise<void> {
  if (isMockMode()) return;
  await apiFetch("/api/users/invitations", {
    method: "POST",
    body: JSON.stringify({ email, role }),
  });
}

export async function updateUser(
  userId: string,
  changes: { role?: User["role"]; is_active?: boolean }
): Promise<User> {
  if (isMockMode()) {
    const existing = mockUserDirectory.find((user) => user.id === userId);
    if (!existing) throw new Error("未找到用户");
    return { ...existing, ...changes };
  }
  return apiFetch<User>(`/api/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(changes),
  });
}

export async function sendUserPasswordReset(userId: string): Promise<void> {
  if (isMockMode()) return;
  await apiFetch(`/api/users/${userId}/password-reset`, { method: "POST" });
}

export async function revokeUserApiKeys(userId: string): Promise<void> {
  if (isMockMode()) return;
  await apiFetch(`/api/users/${userId}/api-keys/revoke`, { method: "POST" });
}

export async function listInvitations(): Promise<Invitation[]> {
  if (isMockMode()) return [];
  const result = await apiFetch<{ items: Invitation[] }>("/api/users/invitations");
  return result.items;
}

export async function resendInvitation(invitationId: string): Promise<void> {
  if (isMockMode()) return;
  await apiFetch(`/api/users/invitations/${invitationId}/resend`, {
    method: "POST",
  });
}

export async function revokeInvitation(invitationId: string): Promise<void> {
  if (isMockMode()) return;
  await apiFetch(`/api/users/invitations/${invitationId}`, { method: "DELETE" });
}

export async function exportSimpleReport(paperId: string): Promise<Blob> {
  if (isMockMode()) return new Blob(["Mock 中国自主知识创新（法学论文）评价系统 报告"], { type: "application/pdf" });
  const response = await fetch(`${API_BASE}/api/papers/${paperId}/export/simple`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }
  return response.blob();
}

export async function listEditorialUnits(): Promise<EditorialUnit[]> {
  if (isMockMode()) return mockEditorialUnits;
  const result = await apiFetch<{ items: EditorialUnit[] }>("/api/editorial/units");
  return result.items;
}

export async function listNotifications(): Promise<NotificationItem[]> {
  if (isMockMode()) return [];
  const result = await apiFetch<{ items: NotificationItem[] }>(
    "/api/editorial/notifications"
  );
  return result.items;
}

export async function markNotificationRead(notificationId: string): Promise<void> {
  if (isMockMode()) return;
  await apiFetch(`/api/editorial/notifications/${notificationId}/read`, {
    method: "POST",
  });
}

export async function listEditorialSubmissions(
  options: EditorialSubmissionListQuery = {}
): Promise<EditorialSubmissionPage> {
  if (isMockMode()) {
    const keyword = options.keyword?.trim().toLocaleLowerCase("zh-CN") ?? "";
    const statusGroups = {
      processing: new Set([
        "queued",
        "anonymizing",
        "formal_check",
        "prechecking",
        "journal_fit_check",
        "evaluating",
        "generating_opinions",
        "expert_review",
      ]),
      awaiting_action: new Set([
        "awaiting_anonymization_confirmation",
        "awaiting_formal_check_confirmation",
        "awaiting_precheck_confirmation",
        "awaiting_fit_confirmation",
        "awaiting_editor",
      ]),
      completed: new Set(["sent_for_external_review", "completed"]),
      failed: new Set(["recovering"]),
    };
    const unitRows = options.unitId
      ? mockEditorialSubmissions.filter((item) => item.unit_id === options.unitId)
      : mockEditorialSubmissions;
    const dateFiltered = unitRows.filter((item) => {
      const matchesKeyword =
        !keyword ||
        (item.title ?? "").toLocaleLowerCase("zh-CN").includes(keyword) ||
        (item.external_manuscript_id ?? "")
          .toLocaleLowerCase("zh-CN")
          .includes(keyword);
      const date = item.created_at.slice(0, 10);
      return (
        matchesKeyword &&
        (!options.submittedFrom || date >= options.submittedFrom) &&
        (!options.submittedTo || date <= options.submittedTo)
      );
    });
    const statusCounts = Object.fromEntries(
      Object.entries(statusGroups).map(([key, statuses]) => [
        key,
        dateFiltered.filter((item) => statuses.has(item.status)).length,
      ])
    ) as EditorialSubmissionPage["status_counts"];
    const filtered = options.statusGroup
      ? dateFiltered.filter((item) =>
          statusGroups[options.statusGroup!].has(item.status)
        )
      : dateFiltered;
    const page = options.page ?? 1;
    const pageSize = options.pageSize ?? 20;
    return {
      items: filtered.slice((page - 1) * pageSize, page * pageSize),
      total: filtered.length,
      page,
      page_size: pageSize,
      status_counts: statusCounts,
    };
  }
  const query = new URLSearchParams();
  if (options.unitId) query.set("unit_id", options.unitId);
  if (options.keyword?.trim()) query.set("q", options.keyword.trim());
  if (options.statusGroup) query.set("status_group", options.statusGroup);
  if (options.submittedFrom) query.set("submitted_from", options.submittedFrom);
  if (options.submittedTo) query.set("submitted_to", options.submittedTo);
  query.set("page", String(options.page ?? 1));
  query.set("page_size", String(options.pageSize ?? 20));
  return apiFetch<EditorialSubmissionPage>(
    `/api/editorial/submissions?${query.toString()}`
  );
}

export async function getEditorialSubmission(
  submissionId: string
): Promise<EditorialSubmissionDetail> {
  if (isMockMode()) {
    return { ...mockEditorialSubmissionDetail, id: submissionId };
  }
  return apiFetch<EditorialSubmissionDetail>(
    `/api/editorial/submissions/${submissionId}`
  );
}

export async function uploadEditorialSubmission(
  unitId: string,
  file: File,
  externalManuscriptId?: string
): Promise<{ submission_id: string; status: string }> {
  if (isMockMode()) {
    return { submission_id: "submission-mock-uploaded", status: "queued" };
  }
  const formData = new FormData();
  formData.append("unit_id", unitId);
  formData.append("file", file);
  if (externalManuscriptId) {
    formData.append("external_manuscript_id", externalManuscriptId);
  }
  const response = await fetch(`${API_BASE}/api/editorial/submissions`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });
  if (!response.ok) throw new Error(await readErrorMessage(response));
  return response.json() as Promise<{ submission_id: string; status: string }>;
}

export async function confirmEditorialAnonymization(
  submissionId: string,
  reason: string
): Promise<void> {
  if (isMockMode()) return;
  await apiFetch(`/api/editorial/submissions/${submissionId}/confirm-anonymization`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export async function continueEditorialSubmission(
  submissionId: string,
  stage: "formal_check" | "precheck" | "journal_fit",
  reason: string
): Promise<void> {
  if (isMockMode()) return;
  await apiFetch(`/api/editorial/submissions/${submissionId}/continue`, {
    method: "POST",
    body: JSON.stringify({ stage, reason }),
  });
}

export async function submitEditorialDecision(
  submissionId: string,
  finalDecision: EditorialDecision,
  decisionStage: "pre_review" | "final",
  rationale: string,
  bypassExpertGate: boolean
): Promise<EditorialDecisionRecord> {
  if (isMockMode()) {
    return {
      id: "decision-mock",
      version: 1,
      decision_stage: decisionStage,
      final_decision: finalDecision,
      recommendation_state: "withheld",
      rationale,
      bypassed_expert_gate: bypassExpertGate,
      actor_id: "mock-editor",
      is_locked: true,
      created_at: new Date().toISOString(),
    };
  }
  return apiFetch<EditorialDecisionRecord>(
    `/api/editorial/submissions/${submissionId}/decision`,
    {
      method: "POST",
      body: JSON.stringify({
        decision_stage: decisionStage,
        final_decision: finalDecision,
        rationale: rationale || null,
        bypass_expert_gate: bypassExpertGate,
      }),
    }
  );
}

export function editorialDocumentUrl(
  submissionId: string,
  kind: "original" | "anonymized"
): string {
  return `${API_BASE}/api/editorial/submissions/${submissionId}/documents/${kind}`;
}

export async function getEditorialManuscript(
  submissionId: string
): Promise<AnonymousManuscript> {
  if (isMockMode()) {
    return getExpertManuscript(submissionId);
  }
  return apiFetch<AnonymousManuscript>(
    `/api/editorial/submissions/${submissionId}/manuscript`
  );
}

export function editorialReportUrl(
  submissionId: string,
  format: "json" | "pdf"
): string {
  return `${API_BASE}/api/editorial/submissions/${submissionId}/report?format=${format}`;
}

export async function listEditorialPolicies(): Promise<string[]> {
  if (isMockMode()) {
    return [
      "jiaoda-law-v1",
      "academic-monthly-law-v1",
      "oriental-law-v1",
    ];
  }
  const result = await apiFetch<{ items: string[] }>(
    "/api/admin/editorial/policies"
  );
  return result.items;
}

export async function listModelSets(): Promise<ModelSet[]> {
  if (isMockMode()) {
    return [
      {
        name: "six-dimension-v1",
        status: "production",
        provider_names: [
          "glm-5.1",
          "qwen3.6-plus",
          "deepseek-v4-pro",
          "kimi-k2.6",
        ],
        review_protocol: "six_dimension_cross_review",
        review_mode: "opposite_groups",
        model_groups: {
          lenient: ["glm-5.1", "qwen3.6-plus"],
          strict: ["deepseek-v4-pro", "kimi-k2.6"],
        },
      },
      {
        name: "six-dimension-v2-candidate",
        status: "candidate-unvalidated",
        provider_names: [
          "glm-5.2",
          "qwen3.7-max-2026-06-08",
          "deepseek-v4-pro",
          "kimi-k2.6",
        ],
        review_protocol: "six_dimension_peer_review",
        review_mode: "all_peers",
      },
    ];
  }
  const result = await apiFetch<{ items: ModelSet[] }>(
    "/api/admin/editorial/model-sets"
  );
  return result.items;
}

export async function startCandidateModelRun(
  submissionId: string
): Promise<{ task_id: string; comparison_group_id: string }> {
  if (isMockMode()) {
    return {
      task_id: "candidate-task-mock",
      comparison_group_id: "comparison-group-mock",
    };
  }
  return apiFetch<{ task_id: string; comparison_group_id: string }>(
    `/api/admin/editorial/submissions/${submissionId}/candidate-run`,
    { method: "POST" }
  );
}

export async function createJournal(
  code: string,
  name: string
): Promise<{ id: string }> {
  if (isMockMode()) return { id: `journal-${code}` };
  return apiFetch<{ id: string }>("/api/admin/editorial/journals", {
    method: "POST",
    body: JSON.stringify({ code, name }),
  });
}

export async function createEditorialUnit(
  journalId: string,
  code: string,
  name: string,
  policyKey: string
): Promise<EditorialUnit> {
  if (isMockMode()) {
    return {
      id: `unit-${code}`,
      journal_id: journalId,
      journal_name: name,
      code,
      name,
      policy_key: policyKey,
      policy_version: "1.0",
      rollout_state: "shadow",
    };
  }
  return apiFetch<EditorialUnit>("/api/admin/editorial/units", {
    method: "POST",
    body: JSON.stringify({
      journal_id: journalId,
      code,
      name,
      policy_key: policyKey,
    }),
  });
}

export async function addEditorialUnitMember(
  unitId: string,
  userId: string
): Promise<void> {
  if (isMockMode()) return;
  await apiFetch(`/api/admin/editorial/units/${unitId}/members`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId, membership_role: "editor" }),
  });
}

export async function activateEditorialUnit(
  unitId: string,
  reason: string,
  validationRunId: string
): Promise<EditorialUnit> {
  if (isMockMode()) {
    const unit = mockEditorialUnits.find((item) => item.id === unitId);
    if (!unit) throw new Error("Editorial unit not found");
    return { ...unit, rollout_state: "active" };
  }
  return apiFetch<EditorialUnit>(
    `/api/admin/editorial/units/${unitId}/rollout`,
    {
      method: "POST",
      body: JSON.stringify({
        rollout_state: "active",
        reason,
        validation_run_id: validationRunId,
        editor_signoff: true,
      }),
    }
  );
}

export async function createValidationRun(
  unitId: string,
  sampleCount: number,
  manifestSha256: string,
  reason: string
): Promise<ValidationRun> {
  if (isMockMode()) {
    return {
      id: "validation-mock",
      unit_id: unitId,
      validation_type: "final_validation",
      framework_version: "law-v2.56.6-20260522",
      model_set_version: "six-dimension-v1",
      sample_manifest_sha256: manifestSha256,
      sample_count: sampleCount,
      metrics: { conclusion: reason },
      status: "draft",
      created_at: new Date().toISOString(),
    };
  }
  return apiFetch<ValidationRun>("/api/admin/editorial/validation-runs", {
    method: "POST",
    body: JSON.stringify({
      unit_id: unitId,
      validation_type: "final_validation",
      framework_version: "law-v2.56.6-20260522",
      model_set_version: "six-dimension-v1",
      sample_manifest_sha256: manifestSha256,
      sample_count: sampleCount,
      metrics: { conclusion: reason },
    }),
  });
}

export async function signValidationRun(runId: string): Promise<ValidationRun> {
  if (isMockMode()) {
    return {
      id: runId,
      unit_id: "unit-jiaoda",
      validation_type: "final_validation",
      framework_version: "law-v2.56.6-20260522",
      model_set_version: "six-dimension-v1",
      sample_manifest_sha256: "0".repeat(64),
      sample_count: 1,
      metrics: {},
      status: "signed",
      signed_at: new Date().toISOString(),
      created_at: new Date().toISOString(),
    };
  }
  return apiFetch<ValidationRun>(
    `/api/admin/editorial/validation-runs/${runId}/sign`,
    { method: "POST" }
  );
}
