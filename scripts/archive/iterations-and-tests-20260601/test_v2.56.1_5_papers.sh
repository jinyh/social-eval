#!/bin/bash
# 测试 v2.56.1（优化后）：5 篇论文 x 4 模型

set -e

echo "=== 测试 v2.56.1：5 篇论文 x 4 模型 ==="
echo "优化内容：analytical_framework 增加理论型论文强制锚定规则"
echo ""

# 使用 Phase 2 的 5 篇论文（排除 paper 7）
PAPER_IDS=(8 4 1 10 6)

# 使用已有的测试脚本
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "开始测试..."
.venv/bin/python scripts/test_v2.56_5_papers.py

echo ""
echo "=== 测试完成 ==="
echo "结果文件：results/v2.56-test-5-papers/raw_results_*.json"
echo ""
echo "运行对比分析："
echo "  python scripts/compare_v2.55_v2.56.py"
