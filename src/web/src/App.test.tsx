import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { submitReview } from "./lib/api";

describe("App", () => {
  it("shows the login form when there is no authenticated user", () => {
    render(<App initialUser={null} />);

    expect(screen.getByRole("heading", { name: /socialeval login/i })).toBeInTheDocument();
  });

  it("shows the submitter portal for submitter users", () => {
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

    expect(screen.getByText(/学生\/投稿人入口/i)).toBeInTheDocument();
  });

  it("shows the unified review workspace for editor users", () => {
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

    expect(screen.getByRole("heading", { name: /编辑\/专家评审工作台/i })).toBeInTheDocument();
    expect(screen.getByText(/编辑视角/i)).toBeInTheDocument();
  });

  it("shows the unified review workspace for expert users", () => {
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

    expect(screen.getByRole("heading", { name: /编辑\/专家评审工作台/i })).toBeInTheDocument();
    expect(screen.getByText(/专家视角/i)).toBeInTheDocument();
  });

  it("shows the admin workspace for admin users", () => {
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

    expect(screen.getByRole("heading", { name: /内部后台/i })).toBeInTheDocument();
  });

  it("renders mock student report with radar and six-dimension breakdown", async () => {
    window.history.pushState({}, "", "/?mock=submitter");

    render(<App initialUser={undefined} />);

    expect(await screen.findByText(/给学生\/投稿人的摘要/i)).toBeInTheDocument();
    expect(screen.getByTestId("dimension-radar-chart")).toBeInTheDocument();
    expect(screen.getByTestId("dimension-breakdown-list")).toBeInTheDocument();
    expect(screen.getAllByText(/问题创新性/i)[0]).toBeInTheDocument();
  });

  it("shows the login page explicitly in mock login mode", async () => {
    window.history.pushState({}, "", "/?mock=login");

    render(<App initialUser={undefined} />);

    expect(await screen.findByRole("heading", { name: /socialeval login/i })).toBeInTheDocument();
  });

  it("anonymizes model names in the internal report mock", async () => {
    window.history.pushState({}, "", "/?mock=editor");

    render(<App initialUser={undefined} />);

    expect((await screen.findAllByText(/模型一/i))[0]).toBeInTheDocument();
    expect(screen.getAllByText(/模型二/i)[0]).toBeInTheDocument();
    expect(screen.getAllByText(/模型三/i)[0]).toBeInTheDocument();
    expect(screen.queryByText(/gpt-5.4/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/glm-5.1/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/qwen/i)).not.toBeInTheDocument();
  });

  it("submits expert review comments without hard-coded scores", async () => {
    const fetchMock = vi.mocked(fetch);
    const comments = [
      {
        dimension_key: "problem_originality",
        ai_score: 82,
        expert_score: 80,
        reason: "认可主判断，但建议微调表述。",
      },
    ];

    await submitReview("review-1", comments);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [, init] = fetchMock.mock.calls.at(-1)!;
    expect(init?.body).toBe(JSON.stringify({ comments }));
  });

  it("does not enable query mock mode in production-like builds", async () => {
    vi.stubEnv("DEV", false);
    vi.stubEnv("VITE_ENABLE_QUERY_MOCKS", "false");
    window.history.pushState({}, "", "/?mock=admin");
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: false,
      status: 401,
      headers: new Headers({ "Content-Type": "application/json" }),
      json: async () => ({}),
      text: async () => "",
    } as Response);

    render(<App initialUser={undefined} />);

    expect(await screen.findByRole("heading", { name: /socialeval login/i })).toBeInTheDocument();
  });
});
