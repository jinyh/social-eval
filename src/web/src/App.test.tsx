import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { submitBlindReview } from "./lib/api";

describe("App", () => {
  it("shows the login form when there is no authenticated user", () => {
    render(<App initialUser={null} />);

    expect(screen.getByRole("heading", { name: /中国自主知识创新.*评价系统/i })).toBeInTheDocument();
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

  it("shows the editorial pre-review workspace for editor users", () => {
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

    expect(screen.getByRole("heading", { name: /编辑工作台/i })).toBeInTheDocument();
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

    expect(screen.getByRole("heading", { name: /专家复核工作台/i })).toBeInTheDocument();
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
    expect(screen.getAllByText(/研究创新性/i)[0]).toBeInTheDocument();
  });

  it("shows the login page explicitly in mock login mode", async () => {
    window.history.pushState({}, "", "/?mock=login");

    render(<App initialUser={undefined} />);

    expect(await screen.findByRole("heading", { name: /中国自主知识创新.*评价系统/i })).toBeInTheDocument();
  });

  it("shows all four anonymous models without exposing provider names", async () => {
    window.history.pushState({}, "", "/?mock=editor");

    render(<App initialUser={undefined} />);

    fireEvent.click(
      await screen.findByRole("button", { name: "投稿管理" })
    );
    fireEvent.click(
      await screen.findByRole("button", {
        name: /平台治理中算法责任的规范结构研究/,
      })
    );
    const reportTab = await screen.findByRole("tab", { name: "评阅报告" });
    expect(reportTab).toHaveAttribute("aria-selected", "true");
    const synthesis = screen.getByRole("heading", {
      name: "智能辅助综合摘要",
    });
    expect(await screen.findByText(/四模型评价/i)).toBeInTheDocument();
    const fiveAxis = screen.getByRole("heading", { name: "五轴位置归属度" });
    const sixDimension = screen.getByRole("heading", { name: "六维学术评价" });
    expect(
      synthesis.compareDocumentPosition(fiveAxis) &
        Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(
      fiveAxis.compareDocumentPosition(sixDimension) &
        Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(screen.getByText("核心问题是否归属于中国法学语境")).toBeInTheDocument();
    expect(screen.getAllByText(/模型甲/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/模型丁/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/glm-5.1/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/qwen3.6-plus/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Choose File|No File Chosen/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("决定阶段")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "处理与决定" }));
    expect(screen.getByText("编辑决定")).toBeInTheDocument();
    expect(screen.getByText("决定阶段")).toBeInTheDocument();
  });

  it("uses a collapsible editor navigation and a separate upload workspace", async () => {
    window.history.pushState({}, "", "/?mock=editor");

    render(<App initialUser={undefined} />);

    expect(
      await screen.findByRole("navigation", { name: "编辑工作台导航" })
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "收起导航栏" }));
    expect(
      screen.getByRole("button", { name: "展开导航栏" })
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "新建投稿" }));
    expect(
      await screen.findByRole("heading", { name: "上传新稿件" })
    ).toBeInTheDocument();
    expect(screen.getByText("尚未选择文件")).toBeInTheDocument();
    expect(screen.queryByText(/Choose File|No File Chosen/i)).not.toBeInTheDocument();
  });

  it("submits expert review comments without hard-coded scores", async () => {
    const fetchMock = vi.mocked(fetch);
    const comments = [
      {
        dimension_key: "problem_originality",
        expert_score: 80,
        reason: "认可主判断，但建议微调表述。",
      },
    ];

    await submitBlindReview("review-1", comments);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1]!;
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

    expect(await screen.findByRole("heading", { name: /中国自主知识创新.*评价系统/i })).toBeInTheDocument();
  });
});
