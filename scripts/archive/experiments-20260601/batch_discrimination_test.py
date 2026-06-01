#!/usr/bin/env python3
"""正负样本区分度测试脚本

所有指标均基于 final_score（v0.16 规程），不基于 legacy weighted_total。
支持快速模式（1 正 + 3 负，~5 分钟）和完整模式（3 正 + 10 负，~20-40 分钟）。

用法：
    # 快速模式
    .venv/bin/python scripts/batch_discrimination_test.py --quick

    # 完整模式
    .venv/bin/python scripts/batch_discrimination_test.py --full

    # 指定框架
    .venv/bin/python scripts/batch_discrimination_test.py --quick \
        --framework configs/frameworks/law-v2.51-20260515.yaml
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

POSITIVE_SAMPLES = [
    "raw/calibration-regression/司法公正与同理心正义_杜宴林.pdf",
    "raw/calibration-regression/比例原则在民法上的适用及展开_郑晓剑.pdf",
    "raw/calibration-regression/国体的起源、构造和选择_中西暗合与差异_佀化强.pdf",
]

NEGATIVE_SAMPLES = [
    "raw/sample/补充负样本/1.邵莉莉 - 2025 - 论绿色溯源法律制度的规范构造.pdf",
    "raw/sample/补充负样本/2.杨清望 - 2025 - 爱国主义法治建设的理论逻辑与实施体系.pdf",
    "raw/sample/补充负样本/3.李雪 - 2026 - 比例原则视角下家庭教育指导令的制度完善.pdf",
    "raw/sample/补充负样本/4.伍德志 - 2023 - 网络社会道德的普泛化及其法律规制.pdf",
    "raw/sample/补充负样本/5.李姝卉 - 2025 - 算法伦理的法律表达.pdf",
    "raw/sample/补充负样本/6.陆青和万子怡 - 2026 - 数字时代人格权商业化利用的法理重构：身份分层理论的展开.pdf",
    "raw/sample/补充负样本/7.包晓丽 - 2025 - 数据产权登记制度的体系构建.pdf",
    "raw/sample/补充负样本/8.娄金炜 - 2026 - 数字化治理背景下行政参与权遮蔽的生成逻辑与制度因应.pdf",
    "raw/sample/补充负样本/9.张涛 - 2024 - 通过算法审计规制自动化决策以社会技术系统理论为视角.pdf",
    "raw/sample/补充负样本/10.崔聪聪 - 2024 - 个人信息监管沙箱的法理基础与制度构建.pdf",
]

DEFAULT_FRAMEWORK = "configs/frameworks/law-v2.50.2-20260514.yaml"
DEFAULT_MODELS = "qwen3.6-plus,glm-5.1"


def run_single_paper(paper_path: str, framework: str, models: str, output_path: Path) -> dict | None:
    """运行单篇论文评测，返回 overall 结果或 None"""
    cmd = [
        ".venv/bin/python", "scripts/run_convergence_test.py",
        "--framework", framework,
        "--paper", paper_path,
        "--output", str(output_path),
        "--models", models,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            with open(output_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get("overall", {})
        else:
            print(f"  ❌ 失败: {result.stderr[:200]}")
            return None
    except subprocess.TimeoutExpired:
        print("  ⏱️ 超时")
        return None
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        return None


def compute_positive_penalty(positive_avg: float) -> float:
    """正样本保护：阶梯式惩罚"""
    if positive_avg >= 85:
        return 0.0
    elif positive_avg >= 80:
        return (85 - positive_avg) * 2
    elif positive_avg >= 75:
        return 10 + (80 - positive_avg) * 5
    else:
        return 35 + (75 - positive_avg) * 10


def compute_discrimination_score(
    positive_scores: list[float],
    negative_scores: list[float],
    positive_pattern_fpr: float = 0.0,
    critical_std_count: int = 0,
) -> dict:
    """计算区分度综合得分"""
    positive_avg = sum(positive_scores) / len(positive_scores) if positive_scores else 0.0
    negative_avg = sum(negative_scores) / len(negative_scores) if negative_scores else 0.0
    negative_below_75_ratio = sum(1 for s in negative_scores if s < 75) / len(negative_scores) if negative_scores else 0.0

    penalty = compute_positive_penalty(positive_avg)

    discrimination_score = (
        (positive_avg - negative_avg)
        + 10 * negative_below_75_ratio
        - penalty
        - 5 * positive_pattern_fpr
        - 2 * critical_std_count
    )

    return {
        "discrimination_score": round(discrimination_score, 2),
        "positive_final_avg": round(positive_avg, 1),
        "negative_final_avg": round(negative_avg, 1),
        "gap": round(positive_avg - negative_avg, 1),
        "negative_below_75_ratio": round(negative_below_75_ratio, 3),
        "positive_penalty": round(penalty, 1),
        "positive_pattern_fpr": round(positive_pattern_fpr, 3),
        "critical_std_count": critical_std_count,
    }


def main():
    parser = argparse.ArgumentParser(description="正负样本区分度测试")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--quick", action="store_true", help="快速模式：1 正 + 3 负")
    mode_group.add_argument("--full", action="store_true", help="完整模式：3 正 + 10 负")
    parser.add_argument("--framework", default=DEFAULT_FRAMEWORK, help="评价框架 YAML 路径")
    parser.add_argument("--models", default=DEFAULT_MODELS, help="模型列表，逗号分隔")
    parser.add_argument("--output-dir", default=None, help="输出目录")
    args = parser.parse_args()

    if args.quick:
        pos_samples = POSITIVE_SAMPLES[:1]
        neg_samples = NEGATIVE_SAMPLES[:3]
        mode_label = "quick"
    else:
        pos_samples = POSITIVE_SAMPLES
        neg_samples = NEGATIVE_SAMPLES
        mode_label = "full"

    framework_name = Path(args.framework).stem
    output_dir = Path(args.output_dir) if args.output_dir else PROJECT_ROOT / "results" / f"discrimination-{framework_name}"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print(f"正负样本区分度测试（{mode_label}）")
    print(f"框架: {args.framework}")
    print(f"模型: {args.models}")
    print(f"正样本: {len(pos_samples)} 篇 | 负样本: {len(neg_samples)} 篇")
    print("主分: final_score（v0.16 规程）")
    print("=" * 60)

    start_time = time.time()
    positive_scores = []
    negative_scores = []
    critical_std_count = 0

    print("\n--- 正样本 ---")
    for i, paper in enumerate(pos_samples, 1):
        paper_name = Path(paper).stem
        print(f"[正{i}/{len(pos_samples)}] {paper_name}")
        out_path = output_dir / f"positive-{i:02d}.json"
        overall = run_single_paper(paper, args.framework, args.models, out_path)
        if overall and overall.get("final_score") is not None:
            positive_scores.append(overall["final_score"])
            if overall.get("max_std", 0) > 12:
                critical_std_count += 1
            print(f"  → final_score={overall['final_score']}, max_std={overall.get('max_std', '?')}")
        else:
            print("  → 跳过（无有效结果）")

    print("\n--- 负样本 ---")
    for i, paper in enumerate(neg_samples, 1):
        paper_name = Path(paper).name.split(" - ")[-1][:30] if " - " in Path(paper).name else Path(paper).stem[:30]
        print(f"[负{i}/{len(neg_samples)}] {paper_name}")
        out_path = output_dir / f"negative-{i:02d}.json"
        overall = run_single_paper(paper, args.framework, args.models, out_path)
        if overall and overall.get("final_score") is not None:
            negative_scores.append(overall["final_score"])
            if overall.get("max_std", 0) > 12:
                critical_std_count += 1
            print(f"  → final_score={overall['final_score']}, max_std={overall.get('max_std', '?')}")
        else:
            print("  → 跳过（无有效结果）")

    elapsed = time.time() - start_time

    if not positive_scores or not negative_scores:
        print("\n❌ 正样本或负样本无有效结果，无法计算区分度")
        return 1

    metrics = compute_discrimination_score(
        positive_scores=positive_scores,
        negative_scores=negative_scores,
        positive_pattern_fpr=0.0,
        critical_std_count=critical_std_count,
    )

    print("\n" + "=" * 60)
    print("区分度测试结果")
    print("=" * 60)
    print(f"  discrimination_score: {metrics['discrimination_score']}")
    print(f"  正样本 final_avg: {metrics['positive_final_avg']}")
    print(f"  负样本 final_avg: {metrics['negative_final_avg']}")
    print(f"  正负差距: {metrics['gap']}")
    print(f"  负样本 < 75 比例: {metrics['negative_below_75_ratio']:.1%}")
    print(f"  正样本惩罚: {metrics['positive_penalty']}")
    print(f"  耗时: {elapsed:.0f} 秒")

    # 保存结果
    result_path = output_dir / f"discrimination-result-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    with open(result_path, 'w', encoding='utf-8') as f:
        json.dump({
            "test_time": datetime.now().isoformat(),
            "mode": mode_label,
            "framework": args.framework,
            "models": args.models.split(","),
            "score_field": "final_score",
            "elapsed_seconds": round(elapsed, 1),
            "positive_scores": positive_scores,
            "negative_scores": negative_scores,
            "metrics": metrics,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存: {result_path}")
    print(f"\ndiscrimination_score: {metrics['discrimination_score']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
