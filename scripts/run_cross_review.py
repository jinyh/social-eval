#!/usr/bin/env python3
"""第二轮交叉评审脚本

让 A 组（GLM/Qwen）和 B 组（DeepSeek/Kimi）互相看到对方的评价意见后重新评分。

用法：
    python scripts/run_cross_review.py \
        --framework configs/frameworks/law-v2.55-cross-review.yaml \
        --round1-dir results/phase1-100-papers-strictest \
        --output-dir results/phase1-100-papers-cross-review \
        --paper-range 1-3 \
        --concurrency 5
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.providers.factory import create_providers
from src.ingestion.preprocessor import process_file
from src.knowledge.loader import _normalize_framework_data, DEFAULT_STD_THRESHOLD
from src.knowledge.schemas import Framework

import yaml

# 模型分组
A_GROUP = ['glm-5.1', 'qwen3.6-plus']
B_GROUP = ['deepseek-v4-pro', 'kimi-k2.6']


def _paper_content(paper) -> str:
    """提取论文正文"""
    return paper.body or paper.full_text


def _reference_content(paper) -> str:
    """提取参考文献"""
    if not paper.references:
        return "（无）"
    return "\n".join(paper.references)


def build_cross_review_prompt(
    dimension_name: str,
    dimension_key: str,
    self_output: dict,
    other_group_outputs: list[dict],
    paper
) -> str:
    """构建交叉评审 prompt

    Args:
        dimension_name: 维度中文名称
        dimension_key: 维度 key
        self_output: 自己的第一轮评价
        other_group_outputs: 对方组的评价（2个模型）
        paper: 论文对象
    """
    # 提取自己的评价
    self_score = self_output.get('score', 0)
    self_band = self_output.get('band', '')
    self_core_judgment = self_output.get('core_judgment', '')
    self_score_rationale = self_output.get('score_rationale', '')
    self_strengths = self_output.get('strengths', [])
    self_weaknesses = self_output.get('weaknesses', [])
    self_evidence_quotes = self_output.get('evidence_quotes', [])

    # 格式化自己的评价
    self_strengths_str = '\n'.join(f'  - {s}' for s in self_strengths) if self_strengths else '  （无）'
    self_weaknesses_str = '\n'.join(f'  - {w}' for w in self_weaknesses) if self_weaknesses else '  （无）'
    self_evidence_str = '\n'.join(f'  - {e}' for e in self_evidence_quotes) if self_evidence_quotes else '  （无）'

    # 构建对方组评价
    other_reviews = []
    for i, other_output in enumerate(other_group_outputs, 1):
        other_score = other_output.get('score', 0)
        other_band = other_output.get('band', '')
        other_core_judgment = other_output.get('core_judgment', '')
        other_score_rationale = other_output.get('score_rationale', '')
        other_strengths = other_output.get('strengths', [])
        other_weaknesses = other_output.get('weaknesses', [])
        other_evidence_quotes = other_output.get('evidence_quotes', [])

        other_strengths_str = '\n'.join(f'  - {s}' for s in other_strengths) if other_strengths else '  （无）'
        other_weaknesses_str = '\n'.join(f'  - {w}' for w in other_weaknesses) if other_weaknesses else '  （无）'
        other_evidence_str = '\n'.join(f'  - {e}' for e in other_evidence_quotes) if other_evidence_quotes else '  （无）'

        review = f"""【评审专家 {chr(64+i)}】
评分：{other_score}
评分档位：{other_band}
核心判断：{other_core_judgment}
评分理由：{other_score_rationale}
优点：
{other_strengths_str}
缺点：
{other_weaknesses_str}
证据引用：
{other_evidence_str}"""
        other_reviews.append(review)

    other_reviews_str = '\n\n'.join(other_reviews)

    # 构建完整 prompt
    prompt = f"""你是一位法学论文评审专家。你之前对这篇论文的【{dimension_name}】维度给出了以下评价：

【你的第一轮评价】
评分：{self_score}
评分档位：{self_band}
核心判断：{self_core_judgment}
评分理由：{self_score_rationale}
优点：
{self_strengths_str}
缺点：
{self_weaknesses_str}
证据引用：
{self_evidence_str}

---

现在，另一组评审专家对同一篇论文的同一维度给出了不同的评价：

{other_reviews_str}

---

请你重新阅读论文原文，结合其他专家的意见，重新审视你的评价：

论文正文：
{_paper_content(paper)}

---
参考文献列表：
{_reference_content(paper)}

---

请仔细思考以下问题：
1. 其他专家的意见中是否有你之前忽略的合理观点？
2. 重新阅读论文后，你是否发现了之前遗漏的证据或论证？
3. 你是否需要修改你的评分？

请输出 JSON：
{{
  "original_score": {self_score},
  "revised_score": <你修改后的评分（如果不修改则与原分相同）>,
  "score_changed": true/false,
  "change_direction": "up" | "down" | "unchanged",
  "change_magnitude": <分数变化的绝对值>,
  "revised_band": "excellent" | "good" | "marginal" | "unacceptable",
  "revised_core_judgment": "重新审视后的核心判断（≤80字）",
  "revision_rationale": "修改理由（如果不修改则说明坚持原判的理由，≤200字）",
  "accepted_points": ["从对方意见中接受的观点"],
  "rejected_points": ["从对方意见中拒绝的观点及理由"],
  "new_evidence_found": ["重新阅读论文后发现的新证据"],
  "confidence": "high" | "medium" | "low"
}}"""

    return prompt


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


async def evaluate_dimension_cross_review(
    dimension_key: str,
    dimension_name: str,
    round1_dim_result: dict,
    paper,
    providers: dict,
    semaphore: asyncio.Semaphore
) -> dict:
    """对单个维度进行交叉评审

    Args:
        dimension_key: 维度 key
        dimension_name: 维度中文名称
        round1_dim_result: 第一轮该维度的结果
        paper: 论文对象
        providers: {model_name: provider}
        semaphore: 并发控制
    """
    round1_raw_outputs = round1_dim_result.get('raw_outputs', {})
    round1_scores = round1_dim_result.get('model_scores', {})

    # 准备交叉评审任务
    tasks = []
    for model_name, provider in providers.items():
        # 确定对方组
        if model_name in A_GROUP:
            other_group = B_GROUP
        else:
            other_group = A_GROUP

        # 提取自己的第一轮评价
        self_output = round1_raw_outputs.get(model_name, {})

        # 提取对方组的第一轮评价
        other_group_outputs = [
            round1_raw_outputs.get(m, {}) for m in other_group
            if m in round1_raw_outputs
        ]

        if not self_output or not other_group_outputs:
            continue

        # 构建 prompt
        prompt = build_cross_review_prompt(
            dimension_name,
            dimension_key,
            self_output,
            other_group_outputs,
            paper
        )

        # 添加任务
        async def call_with_limit(p, pr):
            async with semaphore:
                return await _call_provider(p, pr)

        tasks.append((model_name, call_with_limit(provider, prompt)))

    # 并发调用
    results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=False)

    # 处理结果
    round2_scores = {}
    round2_raw_outputs = {}
    changes = {}
    errors = {}
    elapsed_times = {}

    for (model_name, _), (raw, error, elapsed) in zip(tasks, results):
        elapsed_times[model_name] = elapsed

        if error:
            errors[model_name] = error
            continue

        if not isinstance(raw, dict):
            errors[model_name] = f"Unexpected output type: {type(raw).__name__}"
            continue

        round2_raw_outputs[model_name] = raw

        # 提取修改后的评分
        revised_score = raw.get('revised_score')
        if revised_score is not None:
            round2_scores[model_name] = int(revised_score)

        # 记录变化
        original_score = round1_scores.get(model_name, 0)
        changes[model_name] = {
            'original': original_score,
            'revised': revised_score,
            'changed': raw.get('score_changed', False),
            'direction': raw.get('change_direction', 'unchanged'),
            'magnitude': raw.get('change_magnitude', 0),
            'confidence': raw.get('confidence', 'medium')
        }

    # 计算统计
    round1_mean = round1_dim_result.get('mean', 0)
    round1_std = round1_dim_result.get('std', 0)

    if round2_scores:
        round2_mean = round(statistics.mean(round2_scores.values()), 1)
        round2_std = round(statistics.stdev(round2_scores.values()), 1) if len(round2_scores) > 1 else 0.0
        convergence_improvement = round(round1_std - round2_std, 1)
    else:
        round2_mean = 0
        round2_std = 0
        convergence_improvement = 0

    return {
        'dimension': dimension_key,
        'name_zh': dimension_name,
        'round1_scores': round1_scores,
        'round2_scores': round2_scores,
        'changes': changes,
        'raw_outputs': round2_raw_outputs,
        'errors': errors,
        'elapsed_times': elapsed_times,
        'round1_mean': round1_mean,
        'round2_mean': round2_mean,
        'round1_std': round1_std,
        'round2_std': round2_std,
        'convergence_improvement': convergence_improvement
    }


async def evaluate_paper_cross_review(
    paper_index: int,
    total: int,
    round1_result_path: Path,
    framework: Framework,
    providers: dict,
    output_path: Path,
    semaphore: asyncio.Semaphore
) -> dict | None:
    """对单篇论文进行交叉评审"""
    # 断点续传
    if output_path.exists():
        print(f"[{paper_index}/{total}] {output_path.stem} → 跳过（已完成）")
        with open(output_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    # 加载第一轮结果
    with open(round1_result_path, 'r', encoding='utf-8') as f:
        round1_result = json.load(f)

    paper_path = round1_result.get('paper')
    if not paper_path:
        print(f"[{paper_index}/{total}] {output_path.stem} → 失败：缺少论文路径")
        return None

    paper_name = Path(paper_path).stem[:50]
    print(f"[{paper_index}/{total}] {paper_name} → 开始交叉评审...")

    try:
        # 加载论文原文
        paper = process_file(paper_path)

        # 对每个维度进行交叉评审
        dimension_results = {}
        for dim in framework.dimensions:
            round1_dim_result = round1_result.get('dimensions', {}).get(dim.key)
            if not round1_dim_result:
                continue

            dim_result = await evaluate_dimension_cross_review(
                dim.key,
                dim.name_zh,
                round1_dim_result,
                paper,
                providers,
                semaphore
            )
            dimension_results[dim.key] = dim_result

            # 打印进度
            r1_mean = dim_result['round1_mean']
            r2_mean = dim_result['round2_mean']
            change = r2_mean - r1_mean
            print(f"  {dim.name_zh}: {r1_mean} → {r2_mean} ({change:+.1f})")

        # 计算总体统计
        all_round1_scores = []
        all_round2_scores = []

        for dim_result in dimension_results.values():
            all_round1_scores.extend(dim_result['round1_scores'].values())
            all_round2_scores.extend(dim_result['round2_scores'].values())

        round1_final_score_mean = round(statistics.mean(all_round1_scores), 2) if all_round1_scores else 0
        round2_final_score_mean = round(statistics.mean(all_round2_scores), 2) if all_round2_scores else 0

        # 计算各组变化
        a_group_changes = []
        b_group_changes = []

        for dim_result in dimension_results.values():
            for model_name, change_info in dim_result['changes'].items():
                if change_info['revised'] is not None and change_info['original'] is not None:
                    diff = change_info['revised'] - change_info['original']
                    if model_name in A_GROUP:
                        a_group_changes.append(diff)
                    else:
                        b_group_changes.append(diff)

        avg_change_a = round(statistics.mean(a_group_changes), 1) if a_group_changes else 0
        avg_change_b = round(statistics.mean(b_group_changes), 1) if b_group_changes else 0

        # 构建结果
        result = {
            'paper': paper_path,
            'round1_source': str(round1_result_path),
            'framework': round1_result.get('framework'),
            'models': list(providers.keys()),
            'dimensions': dimension_results,
            'overall': {
                'round1_final_score_mean': round1_final_score_mean,
                'round2_final_score_mean': round2_final_score_mean,
                'group_changes': {
                    'a_group': {
                        'avg_change': avg_change_a,
                        'models': A_GROUP
                    },
                    'b_group': {
                        'avg_change': avg_change_b,
                        'models': B_GROUP
                    }
                }
            }
        }

        # 保存结果
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')

        print(f"[{paper_index}/{total}] {paper_name} → 完成 (A组: {avg_change_a:+.1f}, B组: {avg_change_b:+.1f})")

        return result

    except Exception as e:
        print(f"[{paper_index}/{total}] {paper_name} → 失败: {e}")
        return None


def _load_framework(framework_path: str) -> Framework:
    """加载框架配置"""
    data = yaml.safe_load(Path(framework_path).read_text(encoding="utf-8"))
    if "std_threshold" not in data:
        data["std_threshold"] = DEFAULT_STD_THRESHOLD
    normalized = _normalize_framework_data(data)
    return Framework(**normalized)


async def main():
    parser = argparse.ArgumentParser(description='第二轮交叉评审脚本')
    parser.add_argument('--framework', required=True, help='框架配置文件路径')
    parser.add_argument('--round1-dir', required=True, help='第一轮结果目录')
    parser.add_argument('--output-dir', required=True, help='输出目录')
    parser.add_argument('--paper-range', help='论文范围，如 1-3 或 1-100')
    parser.add_argument('--concurrency', type=int, default=5, help='并发数')

    args = parser.parse_args()

    # 加载框架
    framework = _load_framework(args.framework)

    # 创建 providers
    model_names = A_GROUP + B_GROUP
    providers_list = create_providers(model_names)
    providers = {p.model_name: p for p in providers_list}

    # 获取第一轮结果文件列表
    round1_dir = Path(args.round1_dir)
    round1_files = sorted(round1_dir.glob('paper-*.json'))

    # 过滤论文范围
    if args.paper_range:
        start, end = map(int, args.paper_range.split('-'))
        round1_files = [f for f in round1_files if start <= int(f.stem.split('-')[1]) <= end]

    total = len(round1_files)
    print(f"开始交叉评审：{total} 篇论文")
    print(f"框架：{args.framework}")
    print(f"模型：{', '.join(model_names)}")
    print(f"并发数：{args.concurrency}")
    print()

    # 并发控制
    semaphore = asyncio.Semaphore(10)  # API 总并发限制
    paper_semaphore = asyncio.Semaphore(args.concurrency)  # 论文级并发

    # 创建任务
    tasks = []
    for i, round1_file in enumerate(round1_files, 1):
        output_path = Path(args.output_dir) / round1_file.name

        async def evaluate_with_limit(idx, r1_file, out_path):
            async with paper_semaphore:
                return await evaluate_paper_cross_review(
                    idx, total, r1_file, framework, providers, out_path, semaphore
                )

        tasks.append(evaluate_with_limit(i, round1_file, output_path))

    # 执行
    start_time = time.time()
    results = await asyncio.gather(*tasks, return_exceptions=False)
    elapsed = time.time() - start_time

    # 统计
    success_count = sum(1 for r in results if r is not None)
    print()
    print("=" * 80)
    print(f"交叉评审完成：{success_count}/{total} 篇成功")
    print(f"总耗时：{elapsed/60:.1f} 分钟")
    print(f"输出目录：{args.output_dir}")
    print("=" * 80)


if __name__ == '__main__':
    asyncio.run(main())
