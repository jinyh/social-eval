"""v2.48 增强版三模型迭代收敛测试脚本

在 v2.47 基础上增加"致命缺陷"检测指引，提升顶刊论文区分度。

新增功能：
- --enhanced-guidance: 注入致命缺陷检测指引（教科书式梳理、理论贴标签、逻辑脱节、简单列举）
- 自动标记是否使用增强模式（v2.48_enhanced 字段）

用法：
    # 标准模式（与 v2.47 相同）
    python scripts/run_convergence_test_v2.48.py \
        --framework configs/frameworks/law-v2.47-20260511.yaml \
        --paper raw/sample/正样本/比例原则位阶秩序的司法适用_蒋红珍.pdf \
        --models glm-5.1,qwen3.6-plus \
        --output results/v2.48-test/positive-1-baseline.json

    # v2.48 增强模式（启用致命缺陷检测）
    python scripts/run_convergence_test_v2.48.py \
        --framework configs/frameworks/law-v2.47-20260511.yaml \
        --paper raw/sample/负样本/对外援助立法论纲_曹俊金.pdf \
        --models glm-5.1,qwen3.6-plus \
        --output results/v2.48-test/negative-1-enhanced.json \
        --enhanced-guidance
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.prompt_builder import build_prompt, build_precheck_prompt
from src.evaluation.providers.factory import create_providers
from src.ingestion.preprocessor import process_file
from src.knowledge.loader import _normalize_framework_data, DEFAULT_STD_THRESHOLD
from src.knowledge.schemas import Framework

import yaml
import jsonschema


def get_v248_enhanced_guidance(dimension_key: str) -> str:
    """v2.48 增强评分指引：致命缺陷检测"""
    guidance_map = {
        "problem_originality": """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【v2.48 增强评分指引 - 问题创新性】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ 在评分前，请先检查以下致命缺陷：

【致命缺陷1：教科书式梳理】
- 触发条件：论文主要是对既有理论、制度或政策的系统归纳，缺乏问题导向的学术研究
- 识别标准：
  ✗ 全文主要是梳理和归纳（历史沿革、现状、域外经验）
  ✗ 论文结构为"概念-现状-问题-对策"但缺乏法学层面的争辩点
  ✗ 教科书式的知识归纳，无明确的法学问题句
  ✗ 只说"填补空白"但未说明为何是问题
- 触发后果：问题创新性上限 60 分
- 示例：
  ✗ 《对外援助立法论纲》：全文主要是立法技术梳理，缺乏可争辩的法学问题
  ✓ 《比例原则位阶秩序的司法适用》：虽有梳理，但明确提出了司法适用类型化的法学问题

请在评分时优先检查此缺陷。如果触发，请在 limit_rule_triggered 中记录。
""",
        "analytical_framework": """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【v2.48 增强评分指引 - 分析框架建构力】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ 在评分前，请先检查以下致命缺陷：

【致命缺陷2：理论贴标签】
- 触发条件：引用多个理论概念但未与具体问题实质联系，理论只作装饰
- 识别标准：
  ✗ 引入理论概念（如"工具理性""超级全景监狱"）但未说明如何用于分析本文问题
  ✗ 理论概念只在引言或文献综述中出现，正文分析未使用
  ✗ 堆砌多个理论术语但未形成分析框架
  ✗ 理论只作为包装或标签，未转化为分析工具
- 触发后果：分析框架建构力上限 55 分
- 示例：
  ✗ 《行政机关采集人脸信息活动的法治因应》：引用"工具理性""超级全景监狱"但未与具体问题实质联系
  ✓ 《迈向公私合作型行政法》：引入"辅助性原则""合作原则"并明确说明如何用于分析公私合作治理

请在评分时优先检查此缺陷。如果触发，请在 limit_rule_triggered 中记录。
""",
        "logical_coherence": """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【v2.48 增强评分指引 - 逻辑严密性】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ 【强制前置步骤：致命缺陷检测】

在执行"推理链完整性检查"和"反驳处理度检查"之前，你必须先完成以下前置检测。
如果触发任一致命缺陷，推理链完整性得分直接降为 ≤2，总分上限 60 分。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
第零步：致命缺陷前置检测（必须在第一步之前完成）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【检测A：问题与对策脱节（"两张皮"）】

执行方法：
1. 列出论文"问题分析"部分提出的具体问题（编号 P1, P2, P3...）
2. 列出论文"对策建议"部分提出的具体方案（编号 S1, S2, S3...）
3. 逐一检查：每个 S 是否明确回应了某个 P？
4. 计算对应率：有明确对应关系的 S 数量 / S 总数

判定规则：
- 对应率 < 50%（即超过一半的对策无法对应到前面的问题）→ 触发"两张皮"
- 触发后果：推理链完整性得分 ≤ 2，总分上限 60 分
- 在 limit_rule_triggered 中记录 rule_id: "logical_coherence.argument_disconnection"

示例：
✗ 论文第三部分指出"立法空白""执法困境""救济不足"三个问题，但第四部分的对策是"完善软硬法结构""加强区域协同""优化数据治理"——对策与问题无法一一对应
✓ 论文第二部分指出"位阶秩序未被贯彻"，第三部分分析"截取式适用的内因"，第四部分分析"外因"——每部分都回应前一部分提出的问题

【检测B：段落跳跃（论证链条断裂）】

执行方法：
1. 阅读论文各主要部分的首尾段落
2. 检查：后一部分的开头是否承接前一部分的结论？
3. 检查：各部分之间是否有过渡句说明"因为前面得出了X，所以接下来讨论Y"？
4. 统计：有多少处部分转换缺少逻辑衔接？

判定规则：
- ≥3 处主要部分转换缺少逻辑衔接 → 触发"段落跳跃"
- 触发后果：推理链完整性得分 ≤ 2，总分上限 60 分
- 在 limit_rule_triggered 中记录 rule_id: "logical_coherence.argument_disconnection"

示例：
✗ 第一部分讲"概念界定"，第二部分突然跳到"域外经验"，第三部分又跳到"制度建议"——各部分之间无逻辑衔接
✓ 第一部分"理论假设"→第二部分"类型化验证"→第三部分"内因分析"→第四部分"外因分析"——每部分承接前一部分

【检测C：对策建议空泛（万能药式建议）】

执行方法：
1. 检查论文的对策/建议部分
2. 判断：这些建议是否可以不加修改地套用到其他任何法学问题上？
3. 判断：建议是否具体到法条、程序、机制或制度设计层面？

判定规则：
- 所有建议都是"完善立法""加强监管""健全机制"等万能药表述，无任何具体制度路径 → 触发"建议空泛"
- 触发后果：推理链完整性得分 ≤ 2，总分上限 60 分

示例：
✗ "应完善相关立法""应加强执法力度""应健全监督机制"——这些建议放到任何法学论文都成立
✓ "在合同效力判断上遵循如下步骤：首先目的正当性…其次适当性…再次必要性…最后均衡性"——具体到操作步骤

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【重要】如果上述检测A、B、C中任一触发，你必须：
1. 将推理链完整性得分设为 ≤ 2
2. 总分上限设为 60 分
3. 在 limit_rule_triggered 中记录
4. 不得因为"论文有推理步骤"就给 excellent 档
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

完成前置检测后，再继续执行原有的"第一步：推理链完整性检查"。
""",
        "literature_insight": """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【v2.48 增强评分指引 - 现状洞察度】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ 【强制前置步骤：文献综述质量检测】

在执行"三要素检查"之前，你必须先完成以下前置检测。
如果触发致命缺陷，三要素中"到达点"最多得 1 分，总分上限 60 分。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
第零步：文献综述质量前置检测（必须在第一步之前完成）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【检测A：观点罗列 vs 研究地图】

区分标准：
- 研究地图（高质量）：
  ✓ 对既有研究进行分类、归纳和评价
  ✓ 指出不同研究之间的争点和分歧
  ✓ 说明既有研究的贡献和局限
  ✓ 构建"到达点→未竟点→本文切入点"的逻辑链

- 观点罗列（低质量）：
  ✗ 只是"XX认为YY，ZZ认为WW，AA认为BB"的堆砌
  ✗ 没有对观点进行分类或评价
  ✗ 没有指出观点之间的争点和分歧
  ✗ 没有说明这些观点与本文问题的关系

执行方法：
1. 找到论文的文献综述部分（可能分散在各章节）
2. 检查：作者是否对引用的观点进行了分析和评价？
3. 检查：作者是否指出了不同观点之间的争点？
4. 检查：作者是否说明了既有研究的具体贡献和具体局限？

判定规则：
- 如果文献综述主要是观点罗列（≥70% 的文献引用只是"XX认为YY"，无分析评价）→ 触发"观点罗列"
- 触发后果：三要素中"到达点"最多得 1 分（部分满足），不得得 2 分
- 总分上限 60 分
- 在 limit_rule_triggered 中记录 rule_id: "literature_insight.simple_enumeration_without_analysis"

示例：
✗ "张三（2020）认为应完善立法，李四（2021）认为应加强执法，王五（2022）认为应健全机制"——纯罗列，无分析
✗ "学界对此问题已有较多研究"后面只列举了几个学者的观点，未说明争点
✓ "学界对比例原则的适用范围形成了两种对立观点：限缩论认为…，扩张论认为…，二者的核心分歧在于…"——有分类、有争点

【检测B：案例/数据使用深度】

区分标准：
- 深度剖析（高质量）：
  ✓ 案例分析揭示规范冲突、制度问题或理论张力
  ✓ 数据分析支撑论文论点，有因果推理
  ✓ 从案例/数据中提炼出可推广的规律或类型

- 简单列举（低质量）：
  ✗ 案例只作为例证，说明"确实存在这个现象"
  ✗ 数据只作为背景，说明"问题很严重"
  ✗ 没有从案例/数据中提炼出规律或类型

判定规则：
- 如果论文引用的案例/数据全部只是简单列举（无深度剖析）→ 触发"简单列举"
- 触发后果：三要素中"到达点"最多得 1 分
- 总分上限 60 分

示例：
✗ "长三角科技创新协同立法具有示范意义"——只说有示范意义，未分析具体解决了什么问题
✓ "汇丰公司案中法院采用了截取式适用，仅诉诸必要性审查，原因在于…"——深度剖析案例的裁判逻辑

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【重要】如果上述检测A或B触发，你必须：
1. 三要素中"到达点"最多得 1 分（部分满足）
2. 总分上限设为 60 分
3. 在 limit_rule_triggered 中记录
4. 不得因为"论文确实引用了文献"就给到达点 2 分
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

完成前置检测后，再继续执行原有的"第一步：研究地图三要素检查"。
"""
    }
    return guidance_map.get(dimension_key, "")


async def _call_provider(provider, prompt: str) -> tuple[dict | None, str | None, float]:
    """调用单个 provider，返回 (raw_json, error, elapsed_seconds)"""
    start = time.time()
    try:
        raw = await provider.generate_json_response(prompt)
        elapsed = time.time() - start
        return raw, None, elapsed
    except Exception as e:
        elapsed = time.time() - start
        return None, str(e), elapsed


async def evaluate_single_dimension(
    providers, dimension, paper, framework_path: str, enhanced_guidance: bool = False
) -> dict:
    """并发调用所有 provider 评估单个维度"""
    prompt = build_prompt(dimension, paper)

    # v2.48 增强：注入致命缺陷检测指引
    if enhanced_guidance:
        additional_guidance = get_v248_enhanced_guidance(dimension.key)
        if additional_guidance:
            prompt = additional_guidance + "\n\n" + prompt

    results = await asyncio.gather(
        *[_call_provider(p, prompt) for p in providers],
        return_exceptions=False,
    )

    scores = {}
    raw_outputs = {}
    errors = {}
    elapsed_times = {}

    for (raw, error, elapsed), provider in zip(results, providers):
        elapsed_times[provider.model_name] = elapsed
        if error:
            errors[provider.model_name] = error
            continue
        raw_outputs[provider.model_name] = raw
        if isinstance(raw, dict):
            score = raw.get("score")
        else:
            # 模型偶尔返回非 dict 格式，记为错误
            errors[provider.model_name] = f"Unexpected output type: {type(raw).__name__}"
            continue
        if score is not None:
            scores[provider.model_name] = int(score)

    # 计算 mean/std/置信度
    score_values = list(scores.values())
    mean = statistics.mean(score_values) if score_values else 0.0
    std = statistics.stdev(score_values) if len(score_values) > 1 else 0.0

    if std <= 5.0:
        confidence = "high"
    elif std <= 8.0:
        confidence = "medium"
    elif std <= 12.0:
        confidence = "low"
    else:
        confidence = "critical"

    return {
        "dimension": dimension.key,
        "name_zh": dimension.name_zh,
        "scores": scores,
        "mean": round(mean, 1),
        "std": round(std, 1),
        "confidence": confidence,
        "raw_outputs": raw_outputs,
        "errors": errors,
        "elapsed_times": elapsed_times,
    }


async def run_precheck(providers, framework, paper) -> dict:
    """运行前置检查"""
    prompt = build_precheck_prompt(framework, paper)

    results = await asyncio.gather(
        *[_call_provider(p, prompt) for p in providers],
        return_exceptions=False,
    )

    precheck_results = {}
    for (raw, error, elapsed), provider in zip(results, providers):
        if error:
            precheck_results[provider.model_name] = {"error": error}
        else:
            precheck_results[provider.model_name] = raw

    return precheck_results


def _load_framework_skip_validation(framework_path: str) -> Framework:
    """加载框架但跳过 schema 验证（YAML 可能缺少部分 schema 必需字段）"""
    data = yaml.safe_load(Path(framework_path).read_text(encoding="utf-8"))
    if "std_threshold" not in data:
        data["std_threshold"] = DEFAULT_STD_THRESHOLD
    normalized = _normalize_framework_data(data)
    return Framework(**normalized)


async def run_convergence_test(
    framework_path: str,
    paper_path: str,
    model_names: list[str],
    dimension_keys: list[str] | None = None,
    include_precheck: bool = True,
    enhanced_guidance: bool = False,  # v2.48 新增参数
) -> dict:
    """运行完整的收敛测试"""
    framework = _load_framework_skip_validation(framework_path)
    paper = process_file(paper_path)
    providers = create_providers(model_names)

    # 确定要评估的维度
    if dimension_keys:
        dimensions = [d for d in framework.dimensions if d.key in dimension_keys]
        if not dimensions:
            raise ValueError(f"未找到维度：{dimension_keys}")
    else:
        dimensions = framework.dimensions

    result = {
        "framework": framework_path,
        "framework_version": framework.version,
        "paper": paper_path,
        "models": model_names,
        "paper_structure_status": paper.structure_status,
        "v2.48_enhanced": enhanced_guidance,  # 标记是否使用增强指引
    }

    # 前置检查（可选）
    if include_precheck and framework.precheck and not dimension_keys:
        print("运行前置检查...")
        result["precheck"] = await run_precheck(providers, framework, paper)
    else:
        result["precheck"] = None

    # 逐维度评估
    dimension_results = {}
    for dim in dimensions:
        print(f"评估维度：{dim.name_zh} ({dim.key})...")
        dim_result = await evaluate_single_dimension(
            providers, dim, paper, framework_path, enhanced_guidance  # v2.48: 传递 enhanced_guidance
        )
        dimension_results[dim.key] = dim_result

        scores_str = ", ".join(
            f"{k}={v}" for k, v in dim_result["scores"].items()
        )
        print(f"  分数：{scores_str} | mean={dim_result['mean']} | std={dim_result['std']} | 置信度={dim_result['confidence']}")

    result["dimensions"] = dimension_results

    # 总体统计
    all_stds = [dr["std"] for dr in dimension_results.values()]
    all_means = [dr["mean"] for dr in dimension_results.values()]
    high_confidence_count = sum(
        1 for dr in dimension_results.values() if dr["confidence"] == "high"
    )

    # 加权总分
    weighted_total = 0.0
    for dim in dimensions:
        dr = dimension_results[dim.key]
        weighted_total += dr["mean"] * dim.weight

    result["overall"] = {
        "avg_std": round(statistics.mean(all_stds) if all_stds else 0.0, 1),
        "max_std": round(max(all_stds) if all_stds else 0.0, 1),
        "weighted_total": round(weighted_total, 1),
        "high_confidence_pct": round(
            high_confidence_count / len(dimension_results) * 100 if dimension_results else 0.0, 1
        ),
        "dimension_count": len(dimension_results),
    }

    # 计算复合得分（用于 autoresearch）
    # composite_score = -avg_std + 10 * high_confidence_ratio
    # 目标：avg_std < 5, high_confidence_ratio > 0.8 → composite_score > 3.0
    high_confidence_ratio = high_confidence_count / len(dimension_results) if dimension_results else 0.0
    composite_score = -result["overall"]["avg_std"] + 10 * high_confidence_ratio
    result["overall"]["composite_score"] = round(composite_score, 2)

    # 最高 std 维度（优先优化目标）
    if dimension_results:
        worst_dim = max(dimension_results.values(), key=lambda d: d["std"])
        result["overall"]["worst_dimension"] = worst_dim["dimension"]
        result["overall"]["worst_std"] = worst_dim["std"]

    return result


def main():
    parser = argparse.ArgumentParser(description="三模型迭代收敛测试")
    parser.add_argument(
        "--framework",
        default="configs/frameworks/law-v2.8-20260423.yaml",
        help="评价框架 YAML 路径",
    )
    parser.add_argument(
        "--paper",
        default="raw/司法公正与同理心正义_杜宴林.pdf",
        help="论文 PDF 路径",
    )
    parser.add_argument(
        "--models",
        default="gpt-5.4,kimi-k2.6,glm-5.1",
        help="模型列表，逗号分隔",
    )
    parser.add_argument(
        "--dimensions",
        default=None,
        help="只评估指定维度，逗号分隔（如 problem_originality）；默认全部",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="输出 JSON 文件路径；默认 results/convergence-test-<timestamp>.json",
    )
    parser.add_argument(
        "--no-precheck",
        action="store_true",
        help="跳过前置检查",
    )
    parser.add_argument(
        "--metric",
        default="standard",
        choices=["standard", "composite"],
        help="输出指标类型：standard=完整JSON，composite=单一复合得分（用于autoresearch）",
    )
    parser.add_argument(
        "--enhanced-guidance",
        action="store_true",
        help="v2.48 增强模式：注入致命缺陷检测指引",
    )

    args = parser.parse_args()

    model_names = args.models.split(",")
    dimension_keys = args.dimensions.split(",") if args.dimensions else None

    if not args.output:
        ts = time.strftime("%Y%m%d-%H%M%S")
        output_dir = PROJECT_ROOT / "results"
        output_dir.mkdir(exist_ok=True)
        args.output = str(output_dir / f"convergence-test-{ts}.json")

    print(f"框架：{args.framework}")
    print(f"论文：{args.paper}")
    print(f"模型：{model_names}")
    print(f"维度：{dimension_keys or '全部'}")
    if args.enhanced_guidance:
        print(f"v2.48 增强模式：✅ 已启用致命缺陷检测")
    print()

    result = asyncio.run(
        run_convergence_test(
            framework_path=args.framework,
            paper_path=args.paper,
            model_names=model_names,
            dimension_keys=dimension_keys,
            include_precheck=not args.no_precheck,
            enhanced_guidance=args.enhanced_guidance,  # v2.48: 传递增强模式参数
        )
    )

    # 写入输出文件
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n结果已保存到：{output_path}")

    # 打印汇总
    overall = result["overall"]

    if args.metric == "composite":
        # Autoresearch 模式：只输出单一数值
        print(f"\ncomposite_score: {overall['composite_score']}")
    else:
        # 标准模式：完整汇总
        print(f"\n=== 汇总 ===")
        print(f"加权总分：{overall['weighted_total']}")
        print(f"平均 std：{overall['avg_std']}")
        print(f"最大 std：{overall['max_std']}")
        print(f"高置信度比例：{overall['high_confidence_pct']}%")
        print(f"复合得分：{overall['composite_score']}")
        if "worst_dimension" in overall:
            print(f"最高 std 维度：{overall['worst_dimension']} (std={overall['worst_std']})")


if __name__ == "__main__":
    main()