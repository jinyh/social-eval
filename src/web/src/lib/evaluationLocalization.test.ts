import { describe, expect, it } from "vitest";

import {
  localizeEvaluationText,
  localizeEvaluationValue,
} from "./evaluationLocalization";

describe("localizeEvaluationValue", () => {
  it("localizes precheck and review enums shown to users", () => {
    expect(localizeEvaluationValue("conditional_pass")).toBe("有条件通过");
    expect(localizeEvaluationValue("enter_six_dimension_review")).toBe(
      "进入六维评审"
    );
    expect(localizeEvaluationValue("obviously_ineligible")).toBe("明显不适格");
    expect(localizeEvaluationValue("evaluation_level")).toBe("评价层复核");
    expect(localizeEvaluationValue("continue")).toBe("继续评审");
    expect(localizeEvaluationValue("good")).toBe("良");
  });

  it("localizes signal judgments", () => {
    expect(localizeEvaluationValue("partial")).toBe("部分满足");
    expect(localizeEvaluationValue("not_applicable")).toBe("不适用");
    expect(localizeEvaluationValue("uncertain")).toBe("不确定");
  });

  it("does not expose unknown machine enums in the editor view", () => {
    expect(localizeEvaluationValue("unknown_machine_state")).toBe("待确认");
  });

  it("localizes band codes embedded in synthesis text", () => {
    expect(localizeEvaluationText("模型甲 excellent，模型乙 good。")).toBe(
      "模型甲 优，模型乙 良。"
    );
    expect(localizeEvaluationText("goodness 不应被替换")).toBe(
      "goodness 不应被替换"
    );
  });
});
