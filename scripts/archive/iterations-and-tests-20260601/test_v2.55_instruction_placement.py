#!/usr/bin/env python3
"""v2.55 实验：指令后置（D 方向）验证

实验目标：验证将负面模式扣分规则放在论文内容之后（利用 recency bias），
能否提升扣分规则的触发率。

对照组：v2.50.2 原始结构（指令 + 论文 + 参考文献）
实验组：指令后置结构（基础指令 + 论文 + 参考文献 + 扣分规则）

成功标准：
- 实验组在目标维度得分比对照组低 10+ 分 → 方向有效
- 得分无显著变化（±5 分内）→ 注意力稀释不是主因
"""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
from src.evaluation.providers.factory import create_providers
from src.evaluation.prompt_builder import build_prompt, _append_context
from src.ingestion.preprocessor import process_file
from src.knowledge.schemas import Dimension

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 后置扣分规则（从 v2.50.2 的 prompt_template 中提取）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ANALYTICAL_FRAMEWORK_POST_RULES = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 【强制检查 - 读完论文后必须执行】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

在给出最终分数前，你必须逐条检查以下负面模式。如果触发，强制降档：

A. 口号式呼吁：统计论文中"应当""必须""需要完善""需要加强"等规范性表述的数量。
   如果≥5处且对应的具体制度方案不足（每个"应当"后无具体法条/程序/规则），
   则框架可操作性得分最高为2（无论前面4项标准满足多少）。

B. 概念堆砌：检查论文核心术语（≥3个）是否每个都有"本文所称XX是指..."的明确定义。
   如果≥2个核心术语无明确定义，
   则框架可操作性得分最高为1（无论前面4项标准满足多少）。

C. 宏观介绍非深度分析：检查论文是否只完成体系介绍而未触及具体问题。
   如果全文无任何具体问题的深入分析（只有宏观框架描述），
   则框架可操作性得分最高为2。

框架可操作性得分 = min(满足的标准数量, 负面模式上限)

⚠️ 你必须在 score_rationale 中明确写出每条负面模式的检查结果（触发/未触发）。
如果未写出检查结果，评分无效。
""".strip()

CONCLUSION_CONSENSUS_POST_RULES = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 【强制检查 - 读完论文后必须执行】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

在给出最终分数前，你必须逐条检查以下负面模式。如果触发，强制降档：

A. 生搬硬套：检查结论是否采用"立法-司法-执法-守法"或类似机械四分法。
   如果采用机械框架且每个方面都无具体论证（只有空泛表述），
   则共同体对话度得分最高为1（因为机械套用无法被学界认真回应）。

B. 万能药式对策：检查对策建议是否全部停留在"完善立法、加强监管、健全机制"层面。
   如果对策≥3条且全部为空泛表述（无具体法条/程序/规则），
   则制度可接受度得分最高为1。

C. 结论不足以支撑主张：检查论文是否提出新理论作为替代方案但未说明优势。
   如果新理论未明确说明相对既有理论的优势，
   则共同体对话度得分最高为2。

⚠️ 你必须在 score_rationale 中明确写出每条负面模式的检查结果（触发/未触发）。
如果未写出检查结果，评分无效。
""".strip()


# 测试样本：选择在 v2.50.2 中这两个维度得分异常高的负样本
SAMPLES = [
    ("raw/sample/补充负样本/1.邵莉莉 - 2025 - 论绿色溯源法律制度的规范构造.pdf",
     {"analytical_framework": 64, "conclusion_consensus": 86}),
    ("raw/sample/补充负样本/2.杨清望 - 2025 - 爱国主义法治建设的理论逻辑与实施体系.pdf",
     {"analytical_framework": 84, "conclusion_consensus": 92}),
    ("raw/sample/补充负样本/10.崔聪聪 - 2024 - 个人信息监管沙箱的法理基础与制度构建.pdf",
     {"analytical_framework": 86, "conclusion_consensus": 92}),
]

# 正样本对照
POSITIVE_SAMPLE = (
    "raw/calibration-regression/比例原则在民法上的适用及展开_郑晓剑.pdf",
    {"analytical_framework": 88, "conclusion_consensus": 85},
)

TARGET_DIMENSIONS = ["analytical_framework", "conclusion_consensus"]
MODEL = "qwen3.6-plus"


def load_framework():
    config_path = Path("configs/frameworks/law-v2.50.2-20260514.yaml")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return config


def get_dimension_config(framework_config: dict, dim_key: str) -> dict:
    for dim in framework_config["dimensions"]:
        if dim["key"] == dim_key:
            return dim
    raise ValueError(f"维度 {dim_key} 不存在")


def build_control_prompt(dim_config: dict, paper) -> str:
    """对照组：原始 v2.50.2 结构"""
    dim = Dimension(
        key=dim_config["key"],
        name_zh=dim_config["name_zh"],
        name_en=dim_config["name_en"],
        weight=dim_config["weight"],
        prompt_template=dim_config["prompt_template"],
    )
    return build_prompt(dim, paper)


def build_experiment_prompt(dim_config: dict, paper, post_rules: str) -> str:
    """实验组：指令后置结构"""
    dim = Dimension(
        key=dim_config["key"],
        name_zh=dim_config["name_zh"],
        name_en=dim_config["name_en"],
        weight=dim_config["weight"],
        prompt_template=dim_config["prompt_template"],
        post_content_instruction=post_rules,
    )
    return build_prompt(dim, paper)


def strip_negative_rules_from_template(dim_key: str, template: str) -> str:
    """从 prompt_template 中移除嵌入的负面模式规则（实验组用基础指令）

    对于实验组，我们把负面规则移到后面，所以需要从原始 template 中去掉。
    但为了简化实验，我们保留原始 template 不变——
    实验组的区别仅在于：在论文内容之后额外追加一份强化版扣分提醒。
    这样可以测试"后置强化提醒"是否比"仅嵌入"更有效。
    """
    return template


POST_RULES = {
    "analytical_framework": ANALYTICAL_FRAMEWORK_POST_RULES,
    "conclusion_consensus": CONCLUSION_CONSENSUS_POST_RULES,
}


async def evaluate_single(provider, prompt: str) -> dict | None:
    """调用 provider 评估，返回解析后的结果"""
    try:
        result = await asyncio.wait_for(
            provider.evaluate_dimension(prompt),
            timeout=120.0,
        )
        return result.model_dump()
    except Exception as e:
        print(f"  ❌ 调用失败: {e}")
        return None


async def test_paper(provider, framework_config, paper_path: str, paper_name: str):
    """测试单篇论文：对照组 vs 实验组"""
    print(f"\n{'='*70}")
    print(f"论文: {paper_name}")
    print(f"{'='*70}")

    paper = process_file(Path(paper_path))
    results = {}

    for dim_key in TARGET_DIMENSIONS:
        dim_config = get_dimension_config(framework_config, dim_key)
        post_rules = POST_RULES[dim_key]

        print(f"\n  维度: {dim_key}")

        # 对照组
        control_prompt = build_control_prompt(dim_config, paper)
        print(f"    对照组（原始 v2.50.2）... ", end="", flush=True)
        control_result = await evaluate_single(provider, control_prompt)
        if control_result:
            print(f"得分: {control_result['score']}")
        else:
            print("失败")

        # 实验组
        experiment_prompt = build_experiment_prompt(dim_config, paper, post_rules)
        print(f"    实验组（后置扣分提醒）... ", end="", flush=True)
        experiment_result = await evaluate_single(provider, experiment_prompt)
        if experiment_result:
            print(f"得分: {experiment_result['score']}")
        else:
            print("失败")

        # 记录结果
        if control_result and experiment_result:
            diff = experiment_result["score"] - control_result["score"]
            direction = "↓" if diff < 0 else "↑" if diff > 0 else "→"
            print(f"    差异: {diff:+d} {direction}")

        results[dim_key] = {
            "control": control_result,
            "experiment": experiment_result,
        }

    return results


async def main():
    print("=" * 70)
    print("v2.55 实验：指令后置（D 方向）验证")
    print(f"模型: {MODEL}")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    framework_config = load_framework()
    provider = create_providers([MODEL])[0]

    all_results = {}

    # 测试负样本
    print("\n" + "=" * 70)
    print("【负样本测试】预期：实验组得分更低")
    print("=" * 70)

    for paper_path, baseline_scores in SAMPLES:
        paper_name = Path(paper_path).stem
        results = await test_paper(provider, framework_config, paper_path, paper_name)
        all_results[paper_name] = {
            "type": "negative",
            "baseline_v2.50.2": baseline_scores,
            "results": results,
        }

    # 测试正样本
    print("\n" + "=" * 70)
    print("【正样本对照】预期：实验组得分不应大幅下降")
    print("=" * 70)

    paper_path, baseline_scores = POSITIVE_SAMPLE
    paper_name = Path(paper_path).stem
    results = await test_paper(provider, framework_config, paper_path, paper_name)
    all_results[paper_name] = {
        "type": "positive",
        "baseline_v2.50.2": baseline_scores,
        "results": results,
    }

    # 汇总
    print("\n" + "=" * 70)
    print("实验结果汇总")
    print("=" * 70)

    print(f"\n{'论文':<20} {'维度':<25} {'对照组':>6} {'实验组':>6} {'差异':>6}")
    print("-" * 70)

    effective_count = 0
    total_count = 0

    for paper_name, data in all_results.items():
        for dim_key in TARGET_DIMENSIONS:
            r = data["results"].get(dim_key, {})
            ctrl = r.get("control", {})
            exp = r.get("experiment", {})
            if ctrl and exp:
                ctrl_score = ctrl["score"]
                exp_score = exp["score"]
                diff = exp_score - ctrl_score
                short_name = paper_name[:18]
                print(f"{short_name:<20} {dim_key:<25} {ctrl_score:>6} {exp_score:>6} {diff:>+6}")

                if data["type"] == "negative" and diff <= -10:
                    effective_count += 1
                if data["type"] == "negative":
                    total_count += 1

    print("-" * 70)
    if total_count > 0:
        print(f"\n负样本有效降分率: {effective_count}/{total_count} = {effective_count/total_count:.0%}")
        print(f"（有效 = 实验组比对照组低 10+ 分）")

    # 判断结论
    print("\n" + "=" * 70)
    print("实验结论")
    print("=" * 70)

    if total_count > 0 and effective_count / total_count >= 0.5:
        print("✅ D 方向有效：指令后置显著提升了扣分规则触发率")
        print("   建议：将此策略正式纳入 v2.55 框架")
    elif total_count > 0 and effective_count / total_count > 0:
        print("⚠️ D 方向部分有效：部分样本有改善，但不够稳定")
        print("   建议：结合 E 方向（强化 CoT）进一步优化")
    else:
        print("❌ D 方向无效：注意力稀释可能不是主因")
        print("   建议：转向 E 方向（强化 CoT 锚定）")

    # 保存结果
    output_dir = Path("results/v2.55-test")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"instruction-placement-{datetime.now().strftime('%Y%m%d-%H%M')}.json"

    save_data = {}
    for paper_name, data in all_results.items():
        save_data[paper_name] = {
            "type": data["type"],
            "baseline_v2.50.2": data["baseline_v2.50.2"],
            "results": {},
        }
        for dim_key, r in data["results"].items():
            save_data[paper_name]["results"][dim_key] = {
                "control_score": r["control"]["score"] if r["control"] else None,
                "experiment_score": r["experiment"]["score"] if r["experiment"] else None,
                "control_rationale": r["control"].get("score_rationale") if r["control"] else None,
                "experiment_rationale": r["experiment"].get("score_rationale") if r["experiment"] else None,
            }

    output_file.write_text(json.dumps(save_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已保存: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
