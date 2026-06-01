#!/usr/bin/env python3
"""v2.55 实验：强制 CoT 锚定（E 方向）验证

实验目标：验证"证据提取式 CoT"能否提升负面模式的识别率。
核心思路：不让 AI 判断"是否存在问题"，而是要求 AI 回答"能否找到具体段落"。
找不到 = 扣分，无需 AI 做质量判断。

与 v2.51 的区别：
- v2.51：让 AI 判断"是否存在空泛表述"（抽象判断）→ 失败
- E 方向：让 AI 回答"能否找到具体段落"（具体提取）→ 找不到即扣分

成功标准：
- 负样本在目标维度得分 < 75 → 有效识别
- 正样本得分不应大幅下降（> 80）→ 未误伤
"""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
from src.evaluation.providers.factory import create_providers
from src.evaluation.prompt_builder import _paper_content, _reference_content
from src.ingestion.preprocessor import process_file

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# E 方向：证据提取式 prompt（analytical_framework）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ANALYTICAL_FRAMEWORK_EVIDENCE_COT = """
请对这篇法学论文的【分析框架建构力】进行评分（0-100分）。

【论文类型适配】先判断论文类型，再选择对应的评分参照：
- 理论型论文（法哲学/概念分析类）：理论推演本身即为法学转化，提供概念重构路径即为"操作指引"
- 制度/实务型论文：要求提供裁判规则、法律适用流程或制度设计方案
- 判例型论文：裁判规则归纳、案例分类标准即可作为分析框架
- 比较法论文：比较基准、比较维度和比较方法即为分析框架

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
第一步：证据提取（必须逐条完成，每条必须引用论文原文）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

你必须逐条回答以下问题。每条回答必须直接引用论文原文（用引号标注），
如果找不到对应内容，必须明确写"未找到"。

Q1. 论文是否对核心术语给出了明确定义？
    请引用论文中"本文所称XX是指…"或等效的定义句。
    如果找不到任何核心术语的明确定义 → 写"未找到"。

Q2. 论文是否提出了明确的分类标准或类型划分？
    请引用论文中给出分类依据和边界的段落。
    如果找不到分类标准 → 写"未找到"。

Q3. 论文是否提供了可循的分析步骤或判断流程？
    请引用论文中"第一步…第二步…"或等效的步骤化表述。
    如果找不到步骤化分析流程 → 写"未找到"。

Q4. 框架核心术语/步骤在后文是否被实际调用（≥3处）？
    请引用后文中至少3处使用框架进行分析的段落。
    如果找不到3处以上的调用 → 写"未找到"。

Q5. 跨学科概念是否转化为法学操作步骤？
    请引用论文中将理论概念转化为裁判规则/法律适用流程的段落。
    如果论文未使用跨学科概念 → 写"不适用"。
    如果使用了但未转化 → 写"未找到"。

Q6. 是否提供了裁判规则或操作指引？
    请引用论文中给出具体裁判规则、判断标准或司法适用流程的段落。
    如果找不到 → 写"未找到"。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
第二步：基于证据计分
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

框架可操作性得分（0-4分）：
- Q1 找到明确定义 → +1
- Q2 找到分类标准 → +1
- Q3 找到分析步骤 → +1
- Q4 找到≥3处调用 → +1

法学转化度得分（0-4分）：
- Q5 找到转化步骤（或"不适用"）→ +1
- Q6 找到操作指引 → +1
- Q4 框架在后文被实际使用 → +1（与可操作性共享）
- 制度设计层面有可操作方案 → +1

【强制上限规则】：
- 如果 Q1-Q4 中有 ≥2 条回答"未找到" → 框架可操作性最高 2 分
- 如果 Q1-Q4 中有 ≥3 条回答"未找到" → 框架可操作性最高 1 分
- 如果 Q5+Q6 均回答"未找到" → 法学转化度最高 1 分

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
第三步：确定分数
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

评分锚定规则（先按此规则确定分档，再在档内微调）：

┌──────────┬──────────┬─────────────────┐
│ 可操作性  │ 法学转化度│ 分档             │
├──────────┼──────────┼─────────────────┤
│ ≥3       │ ≥3       │ excellent(80-100)│
│ ≥3       │ 2        │ good(70-79)      │
│ ≥2       │ ≥2       │ good(60-69)      │
│ ≥2       │ ≤1       │ marginal(50-59)  │
│ ≤1       │ 任意     │ unacceptable     │
│          │          │ (0-39)           │
│ 任意     │ ≤1       │ marginal(40-59)  │
└──────────┴──────────┴─────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
输出格式
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

请严格按以下 JSON 格式输出：
{
  "evidence_extraction": {
    "Q1_concept_definition": {"found": true/false, "quote": "引用原文或'未找到'"},
    "Q2_classification": {"found": true/false, "quote": "引用原文或'未找到'"},
    "Q3_analysis_steps": {"found": true/false, "quote": "引用原文或'未找到'"},
    "Q4_framework_usage": {"found": true/false, "quotes": ["引用1", "引用2", "引用3"] 或 "未找到"},
    "Q5_interdisciplinary_transform": {"found": true/false/"not_applicable", "quote": "引用原文"},
    "Q6_operational_guidance": {"found": true/false, "quote": "引用原文或'未找到'"}
  },
  "scoring": {
    "operability_score": 0-4,
    "legal_transform_score": 0-4,
    "score_band": "excellent/good/marginal/unacceptable",
    "forced_cap_applied": true/false,
    "forced_cap_reason": "说明触发了哪条上限规则，或'无'"
  },
  "score": 0-100,
  "score_rationale": "基于证据提取结果的评分理由"
}
""".strip()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# E 方向：证据提取式 prompt（conclusion_consensus）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CONCLUSION_CONSENSUS_EVIDENCE_COT = """
请对这篇法学论文的【结论可接受性】进行评分（0-100分）。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
第零步：判断论文类型
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

先判断论文属于哪类：
- 理论论文：以法哲学、法理学、概念辨析、正当性论证为主
- 制度论文：以实证分析、制度设计、判例分析、比较法为主
- 混合论文：既有理论论证又有制度分析

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
第一步：证据提取（必须逐条完成，每条必须引用论文原文）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

你必须逐条回答以下问题。每条回答必须直接引用论文原文（用引号标注），
如果找不到对应内容，必须明确写"未找到"。

【轨道A：共同体对话度】

Q1. 结论是否明确回应了法学共同体已有争论？
    请引用论文中提及既有学术争论/观点并表明立场的段落。
    如果找不到 → 写"未找到"。

Q2. 结论是否能被反对者定位和回应？
    请引用论文中提出的可被反驳的具体论点（而非"XX很重要"式表态）。
    如果结论只是表态性质 → 写"未找到"。

Q3. 结论是否在中国法学语境中说得通？
    请引用论文中提及中国制度背景/法条/实践的段落。
    如果完全不涉及中国语境 → 写"未找到"。

Q4. 论文是否主动讨论了反对意见或自身局限？
    请引用论文中承认局限或讨论反对意见的段落。
    如果找不到 → 写"未找到"。

【轨道B：制度可接受度】

Q5. 结论是否与现行法秩序兼容（不根本矛盾）？
    请引用论文中表明与现行法秩序关系的段落。
    如果找不到相关讨论 → 写"未找到"。

Q6. 结论是否回应了具体制度/实务约束？
    请引用论文中提及具体法条、程序或制度约束的段落。
    如果找不到 → 写"未找到"。

Q7. 结论是否指出了制度转化的可能方向？
    请引用论文中讨论理论如何落实到制度层面的段落。
    如果找不到 → 写"未找到"。

【负面模式检测】

Q8. 对策建议是否全部停留在空泛层面？
    统计论文中"完善立法""加强监管""健全机制"等空泛对策的数量。
    如果≥3条且全部无具体法条/程序/规则 → 写"是，共N条空泛对策"。
    如果对策有具体内容 → 引用具体对策段落。

Q9. 结论是否采用机械框架（如"立法-司法-执法-守法"四分法）？
    如果采用且每个方面无具体论证 → 写"是"。
    如果未采用或有具体论证 → 写"否"并引用具体论证。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
第二步：基于证据计分
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

共同体对话度得分（0-4分）：
- Q1 找到回应争论 → +1
- Q2 找到可反驳论点 → +1
- Q3 找到中国语境 → +1
- Q4 找到局限讨论 → +1

制度可接受度得分（0-4分）：
- Q5 找到法秩序兼容 → +1
- Q6 找到制度约束回应 → +1
- Q7 找到转化方向 → +1
- Q3 中国语境（与对话度共享）→ +1

【强制上限规则】：
- Q8 回答"是" → 制度可接受度最高 1 分
- Q9 回答"是" → 共同体对话度最高 1 分
- Q1-Q4 中有 ≥3 条"未找到" → 共同体对话度最高 1 分

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
第三步：确定分数
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

制度论文：
┌──────────────┬──────────────┬─────────────────┐
│ 对话度(A)     │ 制度度(B)    │ 分档             │
├──────────────┼──────────────┼─────────────────┤
│ ≥3           │ ≥3           │ excellent(80-100)│
│ ≥3           │ 2            │ good(70-79)      │
│ ≥2           │ ≥2           │ good(60-69)      │
│ ≥2           │ ≤1           │ marginal(50-59)  │
│ ≤1           │ 任意         │ unacceptable(0-49)│
└──────────────┴──────────────┴─────────────────┘

理论论文（轨道B权重降低）：
┌──────────────┬──────────────┬─────────────────┐
│ 对话度(A)     │ 制度度(B)    │ 分档             │
├──────────────┼──────────────┼─────────────────┤
│ ≥3           │ ≥2           │ excellent(80-100)│
│ ≥3           │ 1            │ good(70-79)      │
│ ≥2           │ ≥1           │ good(60-69)      │
│ ≥1           │ ≥1           │ marginal(50-59)  │
│ ≤1 或 B=0    │ 任意         │ unacceptable(0-49)│
└──────────────┴──────────────┴─────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
输出格式
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

请严格按以下 JSON 格式输出：
{
  "paper_type": "理论论文/制度论文/混合论文",
  "evidence_extraction": {
    "Q1_community_debate": {"found": true/false, "quote": "引用原文或'未找到'"},
    "Q2_refutable_claim": {"found": true/false, "quote": "引用原文或'未找到'"},
    "Q3_china_context": {"found": true/false, "quote": "引用原文或'未找到'"},
    "Q4_limitations": {"found": true/false, "quote": "引用原文或'未找到'"},
    "Q5_legal_order_compatible": {"found": true/false, "quote": "引用原文或'未找到'"},
    "Q6_institutional_constraints": {"found": true/false, "quote": "引用原文或'未找到'"},
    "Q7_institutional_direction": {"found": true/false, "quote": "引用原文或'未找到'"},
    "Q8_vague_proposals": {"triggered": true/false, "count": 0, "detail": ""},
    "Q9_mechanical_framework": {"triggered": true/false, "detail": ""}
  },
  "scoring": {
    "dialogue_score": 0-4,
    "institutional_score": 0-4,
    "score_band": "excellent/good/marginal/unacceptable",
    "forced_cap_applied": true/false,
    "forced_cap_reason": "说明触发了哪条上限规则，或'无'"
  },
  "score": 0-100,
  "score_rationale": "基于证据提取结果的评分理由"
}
""".strip()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 测试配置与执行逻辑
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SAMPLES = [
    ("raw/sample/补充负样本/1.邵莉莉 - 2025 - 论绿色溯源法律制度的规范构造.pdf",
     {"analytical_framework": 64, "conclusion_consensus": 86}, "邵莉莉"),
    ("raw/sample/补充负样本/2.杨清望 - 2025 - 爱国主义法治建设的理论逻辑与实施体系.pdf",
     {"analytical_framework": 84, "conclusion_consensus": 92}, "杨清望"),
    ("raw/sample/补充负样本/10.崔聪聪 - 2024 - 个人信息监管沙箱的法理基础与制度构建.pdf",
     {"analytical_framework": 86, "conclusion_consensus": 92}, "崔聪聪"),
]

POSITIVE_SAMPLE = (
    "raw/calibration-regression/比例原则在民法上的适用及展开_郑晓剑.pdf",
    {"analytical_framework": 88, "conclusion_consensus": 85}, "郑晓剑",
)

TARGET_DIMENSIONS = ["analytical_framework", "conclusion_consensus"]
MODEL = "qwen3.6-plus"

EVIDENCE_COT_PROMPTS = {
    "analytical_framework": ANALYTICAL_FRAMEWORK_EVIDENCE_COT,
    "conclusion_consensus": CONCLUSION_CONSENSUS_EVIDENCE_COT,
}


def build_evidence_cot_prompt(dim_key: str, paper) -> str:
    """构建 E 方向的证据提取式 prompt"""
    template = EVIDENCE_COT_PROMPTS[dim_key]
    return (
        f"{template}\n\n"
        f"论文正文：\n{_paper_content(paper)}\n"
        f"---\n"
        f"参考文献列表：\n{_reference_content(paper)}"
    )


async def evaluate_single(provider, prompt: str) -> dict | None:
    """调用 provider 评估，返回结果"""
    try:
        result = await asyncio.wait_for(
            provider.evaluate_dimension(prompt),
            timeout=180.0,
        )
        return result.model_dump()
    except Exception as e:
        print(f"  ❌ 调用失败: {e}")
        return None


async def test_paper(provider, paper_path: str, paper_name: str):
    """测试单篇论文"""
    print(f"\n{'='*70}")
    print(f"论文: {paper_name}")
    print(f"{'='*70}")

    paper = process_file(Path(paper_path))
    results = {}

    for dim_key in TARGET_DIMENSIONS:
        prompt = build_evidence_cot_prompt(dim_key, paper)
        print(f"\n  维度: {dim_key}")
        print(f"    E方向（证据提取式CoT）... ", end="", flush=True)

        result = await evaluate_single(provider, prompt)
        if result:
            print(f"得分: {result.get('score', 'N/A')}")
        else:
            print("失败")

        results[dim_key] = result

    return results


async def main():
    print("=" * 70)
    print("v2.55 实验：强制 CoT 锚定（E 方向）验证")
    print(f"模型: {MODEL}")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    print()
    print("核心假设：将质量判断转化为证据提取任务")
    print("  - 不问'是否存在空泛表述'（抽象判断）")
    print("  - 而问'能否找到具体段落'（具体提取）")
    print("  - 找不到 = 扣分，无需 AI 做质量判断")
    print()

    provider = create_providers([MODEL])[0]
    all_results = {}

    # 测试负样本
    print("\n" + "=" * 70)
    print("【负样本测试】预期：得分 < 75（有效识别）")
    print("=" * 70)

    for paper_path, baseline_scores, name in SAMPLES:
        results = await test_paper(provider, paper_path, name)
        all_results[name] = {
            "type": "negative",
            "baseline_v2.50.2": baseline_scores,
            "results": results,
        }

    # 测试正样本
    print("\n" + "=" * 70)
    print("【正样本对照】预期：得分 > 80（未误伤）")
    print("=" * 70)

    paper_path, baseline_scores, name = POSITIVE_SAMPLE
    results = await test_paper(provider, paper_path, name)
    all_results[name] = {
        "type": "positive",
        "baseline_v2.50.2": baseline_scores,
        "results": results,
    }

    # 汇总
    print("\n" + "=" * 70)
    print("实验结果汇总")
    print("=" * 70)

    print(f"\n{'论文':<10} {'维度':<25} {'v2.50.2基线':>10} {'E方向':>6} {'差异':>6}")
    print("-" * 65)

    effective_neg = 0
    total_neg = 0
    positive_ok = True

    for paper_name, data in all_results.items():
        for dim_key in TARGET_DIMENSIONS:
            r = data["results"].get(dim_key)
            baseline = data["baseline_v2.50.2"].get(dim_key, "?")
            if r:
                score = r.get("score", "?")
                if isinstance(score, (int, float)) and isinstance(baseline, (int, float)):
                    diff = score - baseline
                    direction = "↓" if diff < 0 else "↑" if diff > 0 else "→"
                    print(
                        f"{paper_name:<10} {dim_key:<25} "
                        f"{baseline:>10} {score:>6} {diff:>+6} {direction}"
                    )
                    if data["type"] == "negative":
                        total_neg += 1
                        if score < 75:
                            effective_neg += 1
                    elif data["type"] == "positive" and score < 80:
                        positive_ok = False
                else:
                    print(f"{paper_name:<10} {dim_key:<25} {baseline:>10} {'?':>6}")
            else:
                print(f"{paper_name:<10} {dim_key:<25} {baseline:>10} {'失败':>6}")

    print("-" * 65)
    if total_neg > 0:
        rate = effective_neg / total_neg
        print(f"\n负样本有效识别率: {effective_neg}/{total_neg} = {rate:.0%}")
        print("（有效 = E方向得分 < 75）")
    print(f"正样本安全: {'✅ 未误伤' if positive_ok else '❌ 误伤'}")

    # 判断结论
    print("\n" + "=" * 70)
    print("实验结论")
    print("=" * 70)

    if total_neg > 0 and effective_neg / total_neg >= 0.5 and positive_ok:
        print("✅ E 方向有效：证据提取式 CoT 显著提升了负样本识别率")
        print("   建议：基于此方向设计 v2.56 框架")
    elif total_neg > 0 and effective_neg / total_neg > 0:
        print("⚠️ E 方向部分有效：部分样本有改善")
        if not positive_ok:
            print("   ⚠️ 但正样本被误伤，需调整阈值")
        print("   建议：分析哪些样本有效/无效，针对性优化 prompt")
    else:
        print("❌ E 方向无效：证据提取式 CoT 未能改善识别率")
        print("   建议：考虑 B 方向（两阶段评分）或重新审视问题定义")

    # 保存结果
    output_dir = Path("results/v2.55-test")
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M")
    output_file = output_dir / f"evidence-cot-{ts}.json"

    save_data = {}
    for paper_name, data in all_results.items():
        save_data[paper_name] = {
            "type": data["type"],
            "baseline_v2.50.2": data["baseline_v2.50.2"],
            "results": {},
        }
        for dim_key, r in data["results"].items():
            if r:
                save_data[paper_name]["results"][dim_key] = {
                    "score": r.get("score"),
                    "score_rationale": r.get("score_rationale"),
                    "raw_response": r.get("raw_response", r.get("score_rationale")),
                }
            else:
                save_data[paper_name]["results"][dim_key] = None

    output_file.write_text(
        json.dumps(save_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n结果已保存: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
