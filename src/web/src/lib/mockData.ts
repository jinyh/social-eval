import type {
  InternalReport,
  EditorialSubmissionDetail,
  EditorialSubmissionListItem,
  EditorialUnit,
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
  progress: {
    stage: "report",
    stage_label: "生成报告",
    completed: 35,
    total: 35,
    percent: 100,
    current_dimension: null,
    current_model_slot: null,
    heartbeat_at: "2026-07-24T09:00:00",
    is_stalled: false,
  },
};

const mockDimensions = [
  {
    key: "problem_originality",
    name_zh: "研究创新性",
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
    name_zh: "理论建构力",
    name_en: "Analytical Framework",
    weight: 0.15,
    ai: { mean_score: 74, std_score: 6.1, is_high_confidence: false },
    summary: "框架已经形成责任主体、注意义务与救济路径三层结构，但指标之间的操作化仍需加强。",
  },
  {
    key: "logical_coherence",
    name_zh: "逻辑连贯性",
    name_en: "Logical Coherence",
    weight: 0.25,
    ai: { mean_score: 79, std_score: 4.8, is_high_confidence: true },
    summary: "章节推进较顺畅，主要论证链条清楚，个别反驳部分仍可压实。",
  },
  {
    key: "conclusion_consensus",
    name_zh: "学术共识度",
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
        "moonshot/kimi-k2.6": dimension.ai.mean_score + (index % 2 === 0 ? 1 : -2),
      },
      model_results: ["甲", "乙", "丙", "丁"].map((label, modelIndex) => ({
        model_label: `模型${label}`,
        score: dimension.ai.mean_score + modelIndex - 1.5,
        evidence_quotes: [`第 ${index + 1} 部分的论证可支持该模型判断。`],
        analysis: `${dimension.name_zh}的第 ${modelIndex + 1} 份匿名模型分析。`,
      })),
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
    review_stage: "blind",
    required_dimensions: ["literature_insight", "forward_extension"],
  },
];

export const mockUserDirectory: User[] = [mockUsers.submitter, mockUsers.editor, mockUsers.expert, mockUsers.admin];

export const mockEditorialUnits: EditorialUnit[] = [
  {
    id: "unit-jiaoda",
    journal_id: "journal-jiaoda",
    journal_name: "交大法学",
    code: "default",
    name: "交大法学编辑部",
    policy_key: "jiaoda-law-v1",
    policy_version: "1.0",
    rollout_state: "shadow",
  },
];

export const mockEditorialSubmissions: EditorialSubmissionListItem[] = [
  {
    id: "submission-mock-001",
    unit_id: "unit-jiaoda",
    external_manuscript_id: "JD-2026-001",
    title: "平台治理中算法责任的规范结构研究",
    status: "completed",
    responsible_editor_id: "mock-editor",
    recommendation_state: "withheld",
    current_report_version: 2,
    created_at: "2026-07-24T08:00:00",
    updated_at: "2026-07-24T09:00:00",
  },
];

export const mockEditorialSubmissionDetail: EditorialSubmissionDetail = {
  ...mockEditorialSubmissions[0],
  paper_id: "paper-mock-001",
  task_id: "task-mock-001",
  anonymization_status: "confirmed",
  anonymization_result: {
    redaction_counts: { email: 1, phone: 0, labeled_identity: 2 },
  },
  formal_check_status: "pass",
  formal_check_result: {
    status: "pass",
    character_count: 12000,
    has_section_structure: true,
    has_reference_markers: true,
  },
  precheck_status: "pass",
  precheck_result: { status: "pass" },
  fit_status: "pass",
  fit_result: { status: "pass" },
  internal_candidate_decision: null,
  manual_review_requested: false,
  six_dimension: [
    {
      dimension_key: "problem_originality",
      model_name: "模型一",
      score: 82,
      band: "excellent",
    },
    {
      dimension_key: "logical_coherence",
      model_name: "模型一",
      score: 78,
      band: "good",
    },
  ],
  six_dimension_summary: {
    model_participation: {
      count: 4,
      labels: ["模型甲", "模型乙", "模型丙", "模型丁"],
    },
    difference_count: 1,
    expert_review_dimension_count: 0,
    dimensions: [
      {
        dimension_key: "problem_originality",
        dimension_name: "研究创新性",
        mean_score: 82,
        std_score: 4.2,
        confidence_label: "高",
        band: "excellent",
        band_label: "优",
        difference_level: "consensus",
        difference_label: "意见基本一致",
        requires_expert_review: false,
        model_results: ["甲", "乙", "丙", "丁"].map((label, index) => ({
          model_label: `模型${label}`,
          score: 80 + index,
          band: "excellent",
          band_label: "优",
          evidence_quotes: ["稿件明确提出平台算法责任的规范问题。"],
          analysis: "问题意识较为明确。",
        })),
      },
      {
        dimension_key: "logical_coherence",
        dimension_name: "逻辑连贯性",
        mean_score: 78,
        std_score: 6.2,
        confidence_label: "中等",
        band: "good",
        band_label: "良",
        difference_level: "band_difference",
        difference_label: "存在观点差异",
        requires_expert_review: false,
        model_results: ["甲", "乙", "丙", "丁"].map((label, index) => ({
          model_label: `模型${label}`,
          score: 74 + index * 2,
          band: index < 2 ? "good" : "excellent",
          band_label: index < 2 ? "良" : "优",
          evidence_quotes: ["第三部分对反对观点作出回应。"],
          analysis: "反驳结构的完成度判断存在差异。",
        })),
      },
    ],
  },
  ccb_summary: {
    label: "核心—封顶—加分综合参考分",
    base_score: 79,
    bonus_score: 3,
    ceiling_score: null,
    ceiling_label: "未触发封顶",
    final_score: 82,
    notice: "仅供编辑参考，不作为录用或退稿阈值。",
  },
  position_summary: {
    total_score: 7,
    strength_label: "归属证据中等",
    confidence_label: "中等",
    agreement_label: "两模型存在局部差异",
    review_required: false,
    conflict_with_precheck: false,
    axes: [
      ["对象归属度", "研究问题归属", "核心问题是否归属于中国法学语境"],
      ["材料归属度", "核心材料归属", "材料是否来自中国规范、判例、史料、数据"],
      ["范畴自主度", "分析范畴自主", "核心范畴是否经中国法语境重置"],
      [
        "解释目标归属度",
        "解释目标方向",
        "最终目标是否指向中国法学知识生产",
      ],
      ["体系映射度", "知识体系映射", "知识能否映射到知识树位置"],
    ].map(([axis_name, focus_label, guiding_question], index) => ({
      axis_key: `axis-${index}`,
      axis_name,
      focus_label,
      guiding_question,
      score: index < 2 ? 2 : 1,
      score_range: [1, index < 2 ? 2 : 1],
      evidence_quotes: ["稿件中的中国法材料与制度解释线索。"],
      has_model_difference: index < 2,
    })),
    notice: "五轴评价知识体系位置归属，不评价论文质量，也不参与录退决定。",
  },
  position_assessment: {
    final: { total_score: 7, strength: "medium", review_required: false },
  },
  opinions: [
    {
      id: "opinion-synthesis",
      opinion_type: "ai_synthesis",
      version: 1,
      sequence: 1,
      content: {
        synthesis: "稿件具备明确问题意识，但理论框架与反驳处理仍需加强。",
        consensus_points: ["选题具有现实价值"],
        disagreement_points: ["理论建构完成度判断不同"],
        priority_issues: ["核验核心概念的稳定性"],
      },
      model_name: "模型一",
      is_locked: true,
      created_at: "2026-07-24T09:00:00",
    },
  ],
  model_set_version: "six-dimension-v1",
  review_protocol_version: "six_dimension_cross_review",
  review_protocol_label: "分组交叉复核",
  progress: {
    stage: "report",
    stage_label: "生成报告",
    completed: 44,
    total: 44,
    percent: 100,
    current_dimension: null,
    current_model_slot: null,
    heartbeat_at: "2026-07-24T09:00:00",
    is_stalled: false,
  },
  documents: {
    original: "/api/editorial/submissions/submission-mock-001/documents/original",
    anonymized:
      "/api/editorial/submissions/submission-mock-001/documents/anonymized",
  },
  expert_reviews: [],
  decisions: [],
};

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
