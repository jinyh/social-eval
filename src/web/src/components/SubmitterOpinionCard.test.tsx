import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { SubmitterOpinion } from "@/lib/types";

import { SubmitterOpinionCard } from "./SubmitterOpinionCard";

describe("SubmitterOpinionCard", () => {
  it("renders synthesis and modification suggestions when ready", () => {
    const opinion: SubmitterOpinion = {
      ready: true,
      synthesis: "本稿研究问题明确，但理论建构力有待加强。",
      modification_suggestions: ["补充文献对话", "细化分析步骤"],
    };

    render(<SubmitterOpinionCard opinion={opinion} />);

    expect(
      screen.getByText(/本稿研究问题明确，但理论建构力有待加强/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/补充文献对话/)).toBeInTheDocument();
    expect(screen.getByText(/细化分析步骤/)).toBeInTheDocument();
  });

  it("renders not-ready hint when opinion is not ready", () => {
    const opinion: SubmitterOpinion = {
      ready: false,
      synthesis: "",
      modification_suggestions: [],
    };

    render(<SubmitterOpinionCard opinion={opinion} />);

    expect(screen.getByText(/综合意见尚未生成/)).toBeInTheDocument();
  });
});
