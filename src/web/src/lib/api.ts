import type { PaperListItem, PaperStatus, ReviewQueueItem, ReviewTask, User, UserListResponse } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

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
    const text = await response.text();
    throw new Error(text || `Request failed with ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export async function getCurrentUser(): Promise<User> {
  return apiFetch<User>("/api/auth/me");
}

export async function login(email: string, password: string): Promise<User> {
  return apiFetch<User>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function logout(): Promise<void> {
  await apiFetch<void>("/api/auth/logout", { method: "POST" });
}

export async function listPapers(): Promise<PaperListItem[]> {
  const result = await apiFetch<{ items: PaperListItem[] }>("/api/papers");
  return result.items;
}

export async function uploadPaper(file: File): Promise<{ paper_id: string; task_id: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_BASE}/api/papers`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<{ paper_id: string; task_id: string }>;
}

export async function getPaperStatus(paperId: string): Promise<PaperStatus> {
  return apiFetch<PaperStatus>(`/api/papers/${paperId}/status`);
}

export async function getPublicReport(paperId: string): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>(`/api/papers/${paperId}/report`);
}

export async function getInternalReport(paperId: string): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>(`/api/papers/${paperId}/internal-report`);
}

export async function getReviewQueue(): Promise<ReviewQueueItem[]> {
  const result = await apiFetch<{ items: ReviewQueueItem[] }>("/api/reviews/queue");
  return result.items;
}

export async function listExperts(): Promise<User[]> {
  const result = await apiFetch<UserListResponse>("/api/users/experts");
  return result.items;
}

export async function assignExpert(taskId: string, expertIds: string[]): Promise<void> {
  await apiFetch(`/api/reviews/${taskId}/assign`, {
    method: "POST",
    body: JSON.stringify({ expert_ids: expertIds }),
  });
}

export async function listMyReviews(): Promise<ReviewTask[]> {
  const result = await apiFetch<{ items: ReviewTask[] }>("/api/reviews/mine");
  return result.items;
}

export async function submitReview(reviewId: string): Promise<void> {
  const dimensionKeys = [
    "problem_originality",
    "literature_insight",
    "analytical_framework",
    "logical_coherence",
    "conclusion_consensus",
    "forward_extension",
  ];
  await apiFetch(`/api/reviews/${reviewId}/submit`, {
    method: "POST",
    body: JSON.stringify({
      comments: dimensionKeys.map((dimensionKey) => ({
        dimension_key: dimensionKey,
        ai_score: 70,
        expert_score: 72,
        reason: "Frontend submission",
      })),
    }),
  });
}

export async function listUsers(): Promise<User[]> {
  const result = await apiFetch<UserListResponse>("/api/users");
  return result.items;
}

export async function createInvitation(email: string, role: string): Promise<void> {
  await apiFetch("/api/users/invitations", {
    method: "POST",
    body: JSON.stringify({ email, role }),
  });
}
