import type {
  InternalReport,
  PaperListItem,
  PaperStatus,
  PublicReport,
  ReviewQueueItem,
  ReviewTask,
  User,
} from "./types";

export const mockUsers: Record<User["role"], User> = {
  submitter: { id: "mock-submitter", email: "submitter@example.com", role: "submitter", display_name: "学生用户" },
  editor: { id: "mock-editor", email: "editor@example.com", role: "editor", display_name: "编辑老师" },
  expert: { id: "mock-expert", email: "expert@example.com", role: "expert", display_name: "复核专家" },
  admin: { id: "mock-admin", email: "admin@example.com", role: "admin", display_name: "系统管理员" },
};

export const mockExperts: User[] = [
  mockUsers.expert,
  { id: "mock-expert-2", email: "expert2@example.com", role: "expert", display_name: "外部专家 A" },
];

export const mockPapers: PaperListItem[] = [
  {
    paper_id: "paper-mock-001",
    title: "平台治理中算法责任的规范结构研究",
    original_filename: "algorithm-accountability.pdf",
    paper_status: "completed",
    precheck_status: "passed",
  },
  {
    paper_id: "paper-mock-002",
    title: "生成式人工智能侵权责任的类型化路径",
    original_filename: "ai-tort.docx",
    paper_status: "reviewing",
    precheck_status: "passed",
  },
];

export const mockPaperStatus: PaperStatus = {
  paper_id: "paper-mock-001",
  task_id: "task-mock-001",
  paper_status: "completed",
  task_status: "completed",
  precheck_status: "passed",
  reliability_summary: {
    total_dimensions: 6,
    high_confidence_count: 4,
    low_confidence_count: 2,
    overall_high_confidence: false,
  },
};

const mockDimensions = [
  {
    key: "problem_originality",
    name_zh: "问题创新性",
    name_en: "Problem Originality",
    weight: 0.3,
    ai: { mean_score: 82, std_score: 4.2, is_high_confidence: true },
    summary: "选题聚焦平台治理中的责任分配，能够回应既有规范结构中的真实争议。",
  },
  {
    key: "literature_insight",
    name_zh: "现状洞察度",
    name_en: "Literature Insight",
    weight: 0.15,
    ai: { mean_score: 68, std_score: 9.4, is_high_confidence: false },
    summary: "文献覆盖较完整，但对近三年平台责任与算法透明度交叉研究的辨析不足。",
  },
  {
    key: "analytical_framework",
    name_zh: "分析框架建构力",
    name_en: "Analytical Framework",
    weight: 0.15,
    ai: { mean_score: 74, std_score: 6.1, is_high_confidence: false },
    summary: "框架已经形成责任主体、注意义务与救济路径三层结构，但指标之间的操作化仍需加强。",
  },
  {
    key: "logical_coherence",
    name_zh: "逻辑严密性",
    name_en: "Logical Coherence",
    weight: 0.25,
    ai: { mean_score: 79, std_score: 4.8, is_high_confidence: true },
    summary: "章节推进较顺畅，主要论证链条清楚，个别反驳部分仍可压实。",
  },
  {
    key: "conclusion_consensus",
    name_zh: "结论可接受性",
    name_en: "Conclusion Acceptability",
    weight: 0.1,
    ai: { mean_score: 72, std_score: 5.7, is_high_confidence: false },
    summary: "结论与现行制度框架基本兼容，但对司法适用成本的评估偏弱。",
  },
  {
    key: "forward_extension",
    name_zh: "前瞻延展性",
    name_en: "Forward Extension",
    weight: 0.05,
    ai: { mean_score: 64, std_score: 7.9, is_high_confidence: false },
    summary: "后续研究方向有所提示，但尚未形成清晰的问题地图。",
  },
];

export const mockPublicReport: PublicReport = {
  report_type: "public",
  paper_id: "paper-mock-001",
  task_id: "task-mock-001",
  paper_title: "平台治理中算法责任的规范结构研究",
  weighted_total: 75.8,
  conclusion: "论文具备较好的问题意识和规范分析基础，整体达到建议修改后继续评审的水平。",
  dimensions: mockDimensions,
  expert_conclusion: "建议作者补充最新文献分歧，进一步说明责任规则进入司法适用时的成本与边界。",
  expert_reviews: [
    {
      review_id: "review-mock-001",
      status: "submitted",
      comments: [
        {
          dimension_key: "literature_insight",
          expert_score: 70,
          reason: "文献综述应更明确地区分平台责任、算法透明度与数据治理三条线索。",
        },
      ],
    },
  ],
};

export const mockInternalReport: InternalReport = {
  report_type: "internal",
  paper_id: "paper-mock-001",
  task_id: "task-mock-001",
  paper_title: "平台治理中算法责任的规范结构研究",
  precheck_status: "passed",
  precheck_result: {
    writing: "结构完整，语言表达清晰",
    citation: "未发现明显伪造引用",
    ethics: "未发现高风险学术伦理问题",
  },
  weighted_total: 75.8,
  dimensions: mockDimensions.map((dimension, index) => ({
    ...dimension,
    ai: {
      ...dimension.ai,
      model_scores: {
        "openai/gpt-5.4": dimension.ai.mean_score + (index % 2 === 0 ? 2 : -1),
        "z-ai/glm-5.1": dimension.ai.mean_score - (index % 2 === 0 ? 1 : 4),
        "qwen/qwen3.6-plus": dimension.ai.mean_score + (index % 3 === 0 ? -3 : 3),
      },
      evidence_quotes: [
        [`第 ${index + 1} 部分出现关键论证段落，可支持该维度判断。`],
        [`摘要与结论部分均指向同一规范问题，证据链较集中。`],
      ],
      analysis: [
        `${dimension.name_zh}的模型评价显示：${dimension.summary}`,
        index % 2 === 0
          ? "多个模型对该维度判断较一致，可作为编辑初筛依据。"
          : "该维度模型间分歧较明显，需要专家重点确认。",
      ],
    },
    risk_flags: index % 2 === 0 ? [] : ["低置信度维度", "建议人工复核"],
  })),
  expert_reviews: [
    {
      review_id: "review-mock-001",
      expert_id: "mock-expert",
      status: "pending",
      version: 1,
      completed_at: null,
      comments: [],
    },
  ],
};

export const mockReviewQueue: ReviewQueueItem[] = [
  {
    task_id: "task-mock-001",
    paper_id: "paper-mock-001",
    paper_title: "平台治理中算法责任的规范结构研究",
    paper_status: "reviewing",
    task_status: "reviewing",
    low_confidence_dimensions: ["literature_insight", "forward_extension"],
  },
];

export const mockReviewTasks: ReviewTask[] = [
  {
    review_id: "review-mock-001",
    task_id: "task-mock-001",
    paper_id: "paper-mock-001",
    paper_title: "平台治理中算法责任的规范结构研究",
    status: "pending",
  },
];

export const mockUserDirectory: User[] = [mockUsers.submitter, mockUsers.editor, mockUsers.expert, mockUsers.admin];

export function getMockRole(): User["role"] | null {
  if (!isQueryMockEnabled()) return null;
  if (typeof window === "undefined") return null;
  const params = new URLSearchParams(window.location.search);
  const role = params.get("mock") ?? params.get("role");
  if (role === "submitter" || role === "editor" || role === "expert" || role === "admin") return role;
  if (params.get("mock") === "true") return "submitter";
  return null;
}

export function isMockLoginPage(): boolean {
  if (!isQueryMockEnabled()) return false;
  if (typeof window === "undefined") return false;
  const params = new URLSearchParams(window.location.search);
  return params.get("mock") === "login" || params.get("role") === "login";
}

export function isMockMode(): boolean {
  if (import.meta.env.VITE_USE_MOCKS === "true") return true;
  return getMockRole() !== null || isMockLoginPage();
}

function isQueryMockEnabled(): boolean {
  return import.meta.env.DEV || import.meta.env.VITE_ENABLE_QUERY_MOCKS === "true";
}
