#!/bin/bash
# 全量验证脚本 - 用于最终验证
# 使用 4 篇论文，6 次采样（约 10-15 分钟）

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 使用虚拟环境的 Python
PYTHON="$PROJECT_ROOT/.venv/bin/python"

# 默认参数
FRAMEWORK="${1:-configs/frameworks/law-v2.19-20260424.yaml}"
OUTPUT_DIR="results/autoresearch"

# 创建输出目录
mkdir -p "$OUTPUT_DIR"

# 生成时间戳
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

# 4 篇测试论文
PAPERS=(
    "raw/司法公正与同理心正义_杜宴林.pdf"
    "raw/国体的起源、构造和选择_佀化强.pdf"
    "raw/比例原则在民法上的适用及展开_郑晓剑.pdf"
    "raw/治国理政的法治理念和法治思维_张文显.pdf"
)

echo "=== 全量验证 ==="
echo "框架: $FRAMEWORK"
echo "论文数量: ${#PAPERS[@]}"
echo ""

cd "$PROJECT_ROOT"

# 存储所有 composite_score
SCORES=()

# 逐篇测试
for i in "${!PAPERS[@]}"; do
    PAPER="${PAPERS[$i]}"
    OUTPUT_FILE="$OUTPUT_DIR/full-verify-$TIMESTAMP-paper$((i+1)).json"

    echo "[$((i+1))/${#PAPERS[@]}] 测试: $(basename "$PAPER")"

    $PYTHON scripts/run_convergence_test.py \
        --framework "$FRAMEWORK" \
        --paper "$PAPER" \
        --models "glm-5.1,kimi-k2.6,qwen3.6-plus" \
        --output "$OUTPUT_FILE" \
        --metric composite \
        --no-precheck

    # 提取 composite_score
    SCORE=$($PYTHON -c "import json; print(json.load(open('$OUTPUT_FILE'))['overall']['composite_score'])")
    SCORES+=("$SCORE")

    echo "  Composite Score: $SCORE"
    echo ""
done

# 计算平均 composite_score
AVG_SCORE=$($PYTHON -c "scores = [${SCORES[*]}]; print(round(sum(scores) / len(scores), 2))")

echo "=== 全量验证完成 ==="
echo "各论文得分: ${SCORES[*]}"
echo "平均 Composite Score: $AVG_SCORE"
echo ""

# 保存汇总结果
SUMMARY_FILE="$OUTPUT_DIR/full-verify-$TIMESTAMP-summary.json"
$PYTHON -c "import json; json.dump({'timestamp': '$TIMESTAMP', 'framework': '$FRAMEWORK', 'scores': [${SCORES[*]}], 'avg_score': $AVG_SCORE}, open('$SUMMARY_FILE', 'w'), indent=2)"

echo "汇总结果已保存到: $SUMMARY_FILE"

# 返回平均分（用于判断是否达标）
exit 0
