#!/usr/bin/env python3
"""批量测试 10 篇补充负样本

主分字段：final_score（v0.16 规程）
诊断参考：weighted_total（legacy，仅供参考）
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


def run_test(paper_name: str, index: int, output_dir: Path) -> dict:
    """运行单个测试"""
    paper_path = f"raw/sample/补充负样本/{paper_name}"
    output_path = output_dir / f"negative-{index:02d}.json"

    print(f"\n[{index}/10] 测试: {paper_name}")
    print(f"输出: {output_path}")

    cmd = [
        ".venv/bin/python", "scripts/run_convergence_test.py",
        "--framework", "configs/frameworks/law-v2.50.2-20260514.yaml",
        "--paper", paper_path,
        "--output", str(output_path),
        "--models", "qwen3.6-plus,glm-5.1"
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 分钟超时
        )

        if result.returncode == 0:
            print("✅ 完成")
            # 读取结果
            with open(output_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            overall = data.get("overall", {})
            return {
                "index": index,
                "paper": paper_name,
                "status": "success",
                "final_score": overall.get("final_score"),
                "weighted_total": overall.get("weighted_total"),
                "dimensions": data.get("dimensions", {}),
            }
        else:
            print(f"❌ 失败: {result.stderr}")
            return {
                "index": index,
                "paper": paper_name,
                "status": "failed",
                "error": result.stderr
            }
    except subprocess.TimeoutExpired:
        print("⏱️ 超时")
        return {
            "index": index,
            "paper": paper_name,
            "status": "timeout"
        }
    except Exception as e:
        print(f"❌ 异常: {e}")
        return {
            "index": index,
            "paper": paper_name,
            "status": "error",
            "error": str(e)
        }


def main():
    # 创建输出目录
    output_dir = Path("results/v2.48-optimized")
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("批量测试 10 篇补充负样本")
    print("框架: law-v2.50.2-20260514.yaml")
    print("模型: qwen3.6-plus + glm-5.1")
    print("主分: final_score（v0.16 规程）")
    print("=" * 60)

    results = []
    start_time = datetime.now()

    for i, paper in enumerate(NEGATIVE_SAMPLES, 1):
        result = run_test(paper, i, output_dir)
        results.append(result)

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    # 统计结果
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

    success_count = sum(1 for r in results if r["status"] == "success")
    failed_count = sum(1 for r in results if r["status"] == "failed")
    timeout_count = sum(1 for r in results if r["status"] == "timeout")
    error_count = sum(1 for r in results if r["status"] == "error")

    print(f"总数: {len(results)}")
    print(f"成功: {success_count}")
    print(f"失败: {failed_count}")
    print(f"超时: {timeout_count}")
    print(f"异常: {error_count}")
    print(f"耗时: {duration:.1f} 秒")

    # 计算平均分
    if success_count > 0:
        final_scores = [r["final_score"] for r in results if r["status"] == "success" and r.get("final_score") is not None]
        legacy_scores = [r["weighted_total"] for r in results if r["status"] == "success" and r.get("weighted_total") is not None]
        if final_scores:
            avg_score = sum(final_scores) / len(final_scores)
            min_score = min(final_scores)
            max_score = max(final_scores)
            print("\n负样本得分统计（final_score，主分）:")
            print(f"  平均分: {avg_score:.1f}")
            print(f"  最低分: {min_score:.1f}")
            print(f"  最高分: {max_score:.1f}")
            print(f"  得分 < 75 的比例: {sum(1 for s in final_scores if s < 75) / len(final_scores) * 100:.1f}%")
        if legacy_scores:
            legacy_avg = sum(legacy_scores) / len(legacy_scores)
            print(f"\n  weighted_total（legacy，仅供参考）: 平均 {legacy_avg:.1f}")

    # 保存汇总结果
    summary_path = output_dir / f"batch-test-summary-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump({
            "test_time": start_time.isoformat(),
            "duration_seconds": duration,
            "framework": "law-v2.50.2-20260514.yaml",
            "score_field": "final_score",
            "models": ["qwen3.6-plus", "glm-5.1"],
            "total": len(results),
            "success": success_count,
            "failed": failed_count,
            "timeout": timeout_count,
            "error": error_count,
            "results": results
        }, f, ensure_ascii=False, indent=2)

    print(f"\n汇总结果已保存: {summary_path}")

    return 0 if failed_count == 0 and error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
