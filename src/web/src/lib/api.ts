import type {
  InternalReport,
  ModelSet,
  NotificationItem,
  EditorialDecision,
  EditorialDecisionRecord,
  EditorialSubmissionDetail,
  EditorialSubmissionListItem,
  EditorialUnit,
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

export async function login(email: string, password: string): Promise<User> {
  if (isMockMode()) return mockUsers.submitter;
  return apiFetch<User>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
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

export async function listUsers(): Promise<User[]> {
  if (isMockMode()) return mockUserDirectory;
  const result = await apiFetch<UserListResponse>("/api/users");
  return result.items;
}

export async function createInvitation(email: string, role: string): Promise<void> {
  if (isMockMode()) return;
  await apiFetch("/api/users/invitations", {
    method: "POST",
    body: JSON.stringify({ email, role }),
  });
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
  unitId?: string
): Promise<EditorialSubmissionListItem[]> {
  if (isMockMode()) {
    return unitId
      ? mockEditorialSubmissions.filter((item) => item.unit_id === unitId)
      : mockEditorialSubmissions;
  }
  const query = unitId ? `?unit_id=${encodeURIComponent(unitId)}` : "";
  const result = await apiFetch<{ items: EditorialSubmissionListItem[] }>(
    `/api/editorial/submissions${query}`
  );
  return result.items;
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
        model_groups: {
          lenient: ["glm-5.2", "qwen3.7-max-2026-06-08"],
          strict: ["deepseek-v4-pro", "kimi-k2.6"],
        },
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
