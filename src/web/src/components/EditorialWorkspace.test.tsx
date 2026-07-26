import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  describeEditorialProgress,
  filterEditorialSubmissions,
  GateActionPanel,
} from "./EditorialWorkspace";
import type {
  EditorialSubmissionDetail,
  EditorialSubmissionListItem,
} from "../lib/types";

type ProgressInput = Pick<
  EditorialSubmissionDetail,
  | "status"
  | "anonymization_result"
  | "formal_check_result"
  | "precheck_result"
  | "fit_result"
  | "progress"
>;

function input(overrides: Partial<ProgressInput>): ProgressInput {
  return {
    status: "prechecking",
    anonymization_result: null,
    formal_check_result: null,
    precheck_result: null,
    fit_result: null,
    progress: {
      stage: "precheck",
      stage_label: "公共预检",
      completed: 2,
      total: 62,
      percent: 3,
      is_stalled: false,
    },
    ...overrides,
  };
}

describe("describeEditorialProgress", () => {
  it("shows the formal-check pause reason instead of the next pending stage", () => {
    const result = describeEditorialProgress(
      input({
        status: "awaiting_formal_check_confirmation",
        formal_check_result: {
          issues: ["未识别到参考文献、脚注或注释标记。"],
        },
      })
    );

    expect(result.stageLabel).toBe("待确认形式完整性");
    expect(result.headline).toBe("流程已暂停，等待编辑确认");
    expect(result.detail).toContain("未识别到参考文献、脚注或注释标记");
    expect(result.detail).toContain("填写理由并确认继续");
  });

  it("explains why an active unit has not changed the completed percentage", () => {
    const result = describeEditorialProgress(input({}));

    expect(result.stageLabel).toBe("公共预检中");
    expect(result.headline).toBe("公共预检中");
    expect(result.detail).toContain("正在执行第 3 个处理单元");
    expect(result.detail).toContain("当前单元完成后");
  });
});

describe("GateActionPanel", () => {
  it("明确要求编辑核对匿名稿，并在稿件概览提供确认入口", () => {
    render(
      <GateActionPanel
        detail={
          {
            status: "awaiting_anonymization_confirmation",
          } as EditorialSubmissionDetail
        }
        visible
        gateReason="已核对匿名稿"
        onGateReasonChange={() => undefined}
        onGate={() => undefined}
      />
    );

    expect(
      screen.getByRole("heading", { name: "核对匿名稿后确认是否继续" })
    ).toBeInTheDocument();
    expect(screen.getByText(/匿名稿仍含身份信息时不要确认/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "确认匿名稿无身份信息并继续" })
    ).toBeEnabled();
  });
});

function submission(
  overrides: Partial<EditorialSubmissionListItem>
): EditorialSubmissionListItem {
  return {
    id: "submission-1",
    unit_id: "unit-1",
    external_manuscript_id: "JD-2026-001",
    title: "中国法解释方法研究",
    status: "completed",
    responsible_editor_id: "editor-1",
    recommendation_state: "ready",
    current_report_version: 2,
    created_at: "2026-07-24T16:00:00Z",
    updated_at: "2026-07-25T01:00:00Z",
    ...overrides,
  };
}

describe("filterEditorialSubmissions", () => {
  const rows = [
    submission({}),
    submission({
      id: "submission-2",
      external_manuscript_id: "XM-2026-009",
      title: "数字治理专题",
      status: "evaluating",
      current_report_version: 0,
      created_at: "2026-07-20T02:00:00Z",
    }),
  ];

  it("filters by title or manuscript number and grouped status", () => {
    expect(
      filterEditorialSubmissions(rows, {
        keyword: "JD-2026",
        status: "completed",
        submittedFrom: "",
        submittedTo: "",
      }).map((item) => item.id)
    ).toEqual(["submission-1"]);
  });

  it("filters submission dates in Beijing time inclusively", () => {
    expect(
      filterEditorialSubmissions(rows, {
        keyword: "",
        status: "all",
        submittedFrom: "2026-07-25",
        submittedTo: "2026-07-25",
      }).map((item) => item.id)
    ).toEqual(["submission-1"]);
  });
});
