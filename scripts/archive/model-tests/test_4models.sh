#!/bin/bash
# 多模型对比验证脚本
# 使用 4 个模型：gpt-5.4, glm-5.1, qwen3.6-plus, deepseek-v4-pro

set -e

FRAMEWORK="configs/frameworks/law-v2.40-20260426.yaml"
PAPER="raw/validation/AIGC版权判定的认知经济性分析_蒋舸.pdf"
MODELS="gpt-5.4,glm-5.1,qwen3.6-plus,deepseek-v4-pro"
OUTPUT="results/test-4models.json"

echo "=========================================="
echo "多模型对比验证"
echo "框架: $FRAMEWORK"
echo "论文: $PAPER"
echo "模型: $MODELS"
echo "输出: $OUTPUT"
echo "=========================================="
echo ""

python scripts/run_convergence_test.py \
    --framework "$FRAMEWORK" \
    --paper "$PAPER" \
    --models "$MODELS" \
    --output "$OUTPUT" \
    --no-precheck

echo ""
echo "=========================================="
echo "测试完成！"
echo "=========================================="
echo ""

# 显示关键指标
echo "关键指标："
python3 -c "
import json
data = json.load(open('$OUTPUT'))
overall = data['overall']
print(f\"  平均标准差: {overall['avg_std']:.2f}\")
print(f\"  高置信度比例: {overall['high_confidence_pct']:.1f}%\")
print(f\"  复合得分: {overall['composite_score']:.2f}\")
print(f\"  加权总分: {overall['weighted_total']:.1f}\")
print(f\"  最差维度: {overall['worst_dimension']} (std={overall['max_std']:.2f})\")
"
