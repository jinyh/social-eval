const evaluationValueLabels: Record<string, string> = {
  pass: "通过",
  passed: "通过",
  conditional_pass: "有条件通过",
  manual_review: "需要人工复核",
  boundary: "边界，需确认",
  boundary_review: "边界复核",
  enter_six_dimension_review: "进入六维评审",
  obviously_ineligible: "明显不适格",
  reject: "不通过",
  pending: "待处理",
  processing: "处理中",
  completed: "已完成",
  failed: "处理失败",
  recovering: "等待恢复",
  confirmed: "已确认",
  needs_confirmation: "需要确认",
  comparison: "已完成独立评阅，正在对照",
  submitted: "专家复核已完成",
  returned: "已退回修改",
  required: "必须复核",
  recommended: "建议复核",
  none: "无",
  precheck_level: "预检层复核",
  evaluation_level: "评价层复核",
  enter_six_dim: "进入六维评审",
  boundary_with_review: "边界进入评审并标记复核",
  do_not_enter: "不进入六维评审",
  continue: "继续评审",
  unchanged: "维持原判断",
  increase: "提高",
  decrease: "降低",
  excellent: "优",
  good: "良",
  marginal: "中",
  unacceptable: "差",
  yes: "是",
  no: "否",
  partial: "部分满足",
  uncertain: "不确定",
  sufficient: "充分",
  insufficient: "不足",
  not_applicable: "不适用",
  strong: "强",
  medium: "中等",
  weak: "弱",
  absent: "未发现",
  high: "高",
  low: "较低",
  critical: "很低",
  true: "是",
  false: "否",
};

export function localizeEvaluationValue(value: unknown): string {
  const text = String(value ?? "");
  const localized = evaluationValueLabels[text];
  if (localized) return localized;
  if (!text) return "待确认";
  return /^[A-Za-z][A-Za-z0-9_.-]*$/.test(text) ? "待确认" : text;
}

const bandCodePattern =
  /(^|[^A-Za-z0-9_])(excellent|good|marginal|unacceptable)(?=$|[^A-Za-z0-9_])/gi;

export function localizeEvaluationText(value: unknown): string {
  return String(value ?? "").replace(
    bandCodePattern,
    (_match, prefix: string, code: string) =>
      `${prefix}${evaluationValueLabels[code.toLowerCase()] ?? code}`
  );
}
