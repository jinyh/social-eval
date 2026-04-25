#!/bin/bash
# 快速验证脚本 - 用于 autoresearch 的快速迭代
# 使用单篇论文，3 次采样（约 2-3 分钟）

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 使用虚拟环境的 Python
PYTHON="$PROJECT_ROOT/.venv/bin/python"

# 默认参数
FRAMEWORK="${1:-configs/frameworks/law-v2.19-20260424.yaml}"
PAPER="${2:-raw/比例原则在民法上的适用及展开_郑晓剑.pdf}"
OUTPUT_DIR="results/autoresearch"

# 创建输出目录
mkdir -p "$OUTPUT_DIR"

# 生成时间戳
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTPUT_FILE="$OUTPUT_DIR/quick-verify-$TIMESTAMP.json"

echo "=== 快速验证 ==="
echo "框架: $FRAMEWORK"
echo "论文: $PAPER"
echo "输出: $OUTPUT_FILE"
echo ""

# 运行收敛测试（composite 模式）
cd "$PROJECT_ROOT"
$PYTHON scripts/run_convergence_test.py \
    --framework "$FRAMEWORK" \
    --paper "$PAPER" \
    --models "glm-5.1,gpt-5.4,qwen3.6-plus" \
    --output "$OUTPUT_FILE" \
    --metric composite \
    --no-precheck

# 提取 composite_score
COMPOSITE_SCORE=$($PYTHON -c "import json; print(json.load(open('$OUTPUT_FILE'))['overall']['composite_score'])")

echo ""
echo "=== 验证完成 ==="
echo "Composite Score: $COMPOSITE_SCORE"
echo ""

# 返回 composite_score（用于 autoresearch）
exit 0
