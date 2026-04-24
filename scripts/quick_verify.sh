#!/bin/bash
# 快速验证脚本 - 用于 autoresearch 的快速迭代
# 使用单篇论文，3 次采样（约 2-3 分钟）

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 默认参数
FRAMEWORK="${1:-configs/frameworks/law-v2.19-20260424.yaml}"
PAPER="${2:-raw/司法公正与同理心正义_杜宴林.pdf}"
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
python3 scripts/run_convergence_test.py \
    --framework "$FRAMEWORK" \
    --paper "$PAPER" \
    --models "gpt-5.4,kimi-k2.6,glm-5.1" \
    --output "$OUTPUT_FILE" \
    --metric composite \
    --no-precheck

# 提取 composite_score
COMPOSITE_SCORE=$(python3 -c "import json; print(json.load(open('$OUTPUT_FILE'))['overall']['composite_score'])")

echo ""
echo "=== 验证完成 ==="
echo "Composite Score: $COMPOSITE_SCORE"
echo ""

# 返回 composite_score（用于 autoresearch）
exit 0
