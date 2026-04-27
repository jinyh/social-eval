import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App } from "./App";

describe("App", () => {
  it("shows the login form when there is no authenticated user", () => {
    render(<App initialUser={null} />);

    expect(screen.getByRole("heading", { name: /选择入口后登录/i })).toBeInTheDocument();
  });

  it("shows the submitter dashboard for submitter users", () => {
    render(
      <App
        initialUser={{
          id: "user-1",
          email: "submitter@example.com",
          role: "submitter",
          display_name: "Submitter",
        }}
      />
    );

    expect(screen.getAllByText(/普通学生 \/ 投稿人入口/i).length).toBeGreaterThan(0);
  });

  it("shows the editor dashboard for editor users", () => {
    render(
      <App
        initialUser={{
          id: "user-2",
          email: "editor@example.com",
          role: "editor",
          display_name: "Editor",
        }}
      />
    );

    expect(screen.getByText(/编辑 \/ 专家工作台/i)).toBeInTheDocument();
  });

  it("shows the expert review entry for expert users", () => {
    render(
      <App
        initialUser={{
          id: "user-4",
          email: "expert@example.com",
          role: "expert",
          display_name: "Expert",
        }}
      />
    );

    expect(screen.getByText(/我的复核任务/i)).toBeInTheDocument();
  });

  it("shows the admin dashboard for admin users", () => {
    render(
      <App
        initialUser={{
          id: "user-3",
          email: "admin@example.com",
          role: "admin",
          display_name: "Admin",
        }}
      />
    );

    expect(screen.getByText(/系统管理/i)).toBeInTheDocument();
  });

  it("renders public report fields from the backend shape", async () => {
    vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/papers")) {
        return new Response(
          JSON.stringify({
            items: [
              {
                paper_id: "paper-1",
                title: "测试论文",
                original_filename: "paper.txt",
                paper_status: "completed",
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      if (url.endsWith("/api/papers/paper-1/status")) {
        return new Response(
          JSON.stringify({
            paper_id: "paper-1",
            task_id: "task-1",
            paper_status: "completed",
            task_status: "completed",
            precheck_status: "pass",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      if (url.endsWith("/api/papers/paper-1/report")) {
        return new Response(
          JSON.stringify({
            report_type: "public",
            paper_id: "paper-1",
            task_id: "task-1",
            paper_title: "测试论文",
            weighted_total: 72,
            conclusion: "可进入专家深审",
            dimensions: [
              {
                key: "problem_originality",
                name_zh: "问题创新性",
                name_en: "Problem Originality",
                weight: 0.3,
                summary: "问题意识明确",
                ai: { mean_score: 72, std_score: 4, is_high_confidence: true },
              },
            ],
            expert_reviews: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });

    render(
      <App
        initialUser={{
          id: "user-1",
          email: "submitter@example.com",
          role: "submitter",
          display_name: "Submitter",
        }}
      />
    );

    expect(await screen.findByText("测试论文")).toBeInTheDocument();
    expect(await screen.findByText(/问题意识明确/i)).toBeInTheDocument();
  });
});
