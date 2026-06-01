#!/usr/bin/env python3
"""v2.50.2 框架 + GPT 5.5 high 测试

对比基线：v2.50.2 + qwen3.6-plus/glm-5.1（负样本均值 76.1，正样本 91.1）
本次测试：v2.50.2 + gpt-5.5-high（双模型并发）

测试样本：9 篇负样本 + 1 篇正样本（蒋红珍）
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

NEGATIVE_SAMPLES = [
    "1.邵莉莉 - 2025 - 论绿色溯源法律制度的规范构造.pdf",
    "2.杨清望 - 2025 - 爱国主义法治建设的理论逻辑与实施体系.pdf",
    "3.李雪 - 2026 - 比例原则视角下家庭教育指导令的制度完善.pdf",
    "4.伍德志 - 2023 - 网络社会道德的普泛化及其法律规制.pdf",
    "5.李姝卉 - 2025 - 算法伦理的法律表达.pdf",
    "6.陆青和万子怡 - 2026 - 数字时代人格权商业化利用的法理重构：身份分层理论的展开.pdf",
    "7.包晓丽 - 2025 - 数据产权登记制度的体系构建.pdf",
    "8.娄金炜 - 2026 - 数字化治理背景下行政参与权遮蔽的生成逻辑与制度因应.pdf",
    "9.张涛 - 2024 - 通过算法审计规制自动化决策以社会技术系统理论为视角.pdf",
    "10.崔聪聪 - 2024 - 个人信息监管沙箱的法理基础与制度构建.pdf",
]

POSITIVE_SAMPLES = [
    ("比例原则在民法上的适用及展开_郑晓剑.pdf", "calibration-regression"),
]

FRAMEWORK = "configs/frameworks/law-v2.50.2-20260514.yaml"
MODELS = "gpt-5.5-high,gpt-5.5-high"


def run_test(paper_path: str, label: str, output_path: Path) -> dict:
    """运行单个测试"""
    print(f"\n测试: {label}")
    print(f"  论文: {paper_path}")
    print(f"  输出: {output_path}")

    cmd = [
        ".venv/bin/python", "scripts/run_convergence_test.py",
        "--framework", FRAMEWORK,
        "--paper", paper_path,
        "--output", str(output_path),
        "--models", MODELS,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)

        if result.returncode == 0:
            with open(output_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            overall = data.get("overall", {})
            print(f"  ✅ final_score={overall.get('final_score')} | weighted_total={overall.get('weighted_total')}")
            return {
                "label": label,
                "paper": paper_path,
                "status": "success",
                "final_score": overall.get("final_score"),
                "weighted_total": overall.get("weighted_total"),
                "dimensions": {k: v.get("mean") for k, v in data.get("dimensions", {}).items()},
            }
        else:
            print(f"  ❌ 失败: {result.stderr[-300:]}")
            return {"label": label, "paper": paper_path, "status": "failed", "error": result.stderr[-500:]}
    except subprocess.TimeoutExpired:
        print("  ⏱️ 超时（15分钟）")
        return {"label": label, "paper": paper_path, "status": "timeout"}
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        return {"label": label, "paper": paper_path, "status": "error", "error": str(e)}


def main():
    output_dir = Path("results/v2.50.2-gpt55-high")
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("v2.50.2 + GPT 5.5 high 测试")
    print(f"框架: {FRAMEWORK}")
    print(f"模型: {MODELS}")
    print("=" * 60)

    results = []
    start_time = datetime.now()

    # 负样本
    for i, paper_name in enumerate(NEGATIVE_SAMPLES, 1):
        paper_path = f"raw/sample/补充负样本/{paper_name}"
        output_path = output_dir / f"negative-{i:02d}.json"
        result = run_test(paper_path, f"[负{i:02d}] {paper_name[:20]}", output_path)
        results.append({"type": "negative", **result})

    # 正样本
    for i, (paper_name, subdir) in enumerate(POSITIVE_SAMPLES, 1):
        paper_path = f"raw/{subdir}/{paper_name}"
        output_path = output_dir / f"positive-{i:02d}.json"
        result = run_test(paper_path, f"[正{i:02d}] {paper_name[:20]}", output_path)
        results.append({"type": "positive", **result})

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    # 汇总
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    neg_scores = [r["final_score"] for r in results if r["type"] == "negative" and r.get("final_score") is not None]
    pos_scores = [r["final_score"] for r in results if r["type"] == "positive" and r.get("final_score") is not None]

    if neg_scores:
        avg_neg = sum(neg_scores) / len(neg_scores)
        print(f"\n负样本（{len(neg_scores)} 篇）:")
        print(f"  均值: {avg_neg:.1f}")
        print(f"  范围: {min(neg_scores):.1f} ~ {max(neg_scores):.1f}")
        print(f"  < 75 分: {sum(1 for s in neg_scores if s < 75)}/{len(neg_scores)} ({sum(1 for s in neg_scores if s < 75)/len(neg_scores)*100:.0f}%)")
        print(f"  < 80 分: {sum(1 for s in neg_scores if s < 80)}/{len(neg_scores)} ({sum(1 for s in neg_scores if s < 80)/len(neg_scores)*100:.0f}%)")

    if pos_scores:
        avg_pos = sum(pos_scores) / len(pos_scores)
        print(f"\n正样本（{len(pos_scores)} 篇）:")
        print(f"  均值: {avg_pos:.1f}")

    if neg_scores and pos_scores:
        gap = avg_pos - avg_neg
        print(f"\n正负差距: {avg_pos:.1f} - {avg_neg:.1f} = {gap:.1f}")

    # 对比基线
    print("\n--- 对比基线（qwen3.6-plus + glm-5.1）---")
    print("  负样本均值: 76.1 | 正样本: 91.1 | 差距: 15.0")
    if neg_scores:
        print(f"  本次负样本均值: {avg_neg:.1f} (差异: {avg_neg - 76.1:+.1f})")
    if pos_scores:
        print(f"  本次正样本均值: {avg_pos:.1f} (差异: {avg_pos - 91.1:+.1f})")

    # 逐篇得分
    print("\n--- 逐篇得分 ---")
    for r in results:
        score = r.get("final_score", "N/A")
        marker = "✅" if r["status"] == "success" else "❌"
        print(f"  {marker} {r['label']}: {score}")

    print(f"\n耗时: {duration:.0f} 秒 ({duration/60:.1f} 分钟)")

    # 保存汇总
    summary = {
        "test_time": start_time.isoformat(),
        "duration_seconds": duration,
        "framework": FRAMEWORK,
        "models": MODELS,
        "baseline": {"neg_mean": 76.1, "pos_mean": 91.1, "gap": 15.0, "models": "qwen3.6-plus,glm-5.1"},
        "results": results,
    }
    summary_path = output_dir / "summary.json"
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n汇总已保存: {summary_path}")


if __name__ == "__main__":
    main()
