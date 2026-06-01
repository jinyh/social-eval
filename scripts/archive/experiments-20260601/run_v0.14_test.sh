#!/bin/bash
# v0.14 多模型验证测试 - 快速启动脚本

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "=========================================="
echo "v0.14 多模型验证测试"
echo "=========================================="
echo ""

# 检查环境变量
echo "检查环境变量..."
if [ -z "$DASHSCOPE_API_KEY" ]; then
    echo "⚠️  警告：DASHSCOPE_API_KEY 未设置"
    echo "   请在 .env 文件中配置或运行："
    echo "   export DASHSCOPE_API_KEY=your_key"
fi

if [ -z "$ZENMUX_API_KEY" ]; then
    echo "⚠️  警告：ZENMUX_API_KEY 未设置（默认 GPT 复核模型 gpt-5.4 需要）"
    echo "   如果不需要 GPT 复核，可以使用 --no-gpt-review 参数"
fi

echo ""

# 显示菜单
echo "请选择测试模式："
echo "1. 小规模测试（2 篇，验证脚本和配置）"
echo "2. 完整测试（6 篇，全面评估）"
echo "3. 单篇测试（自定义）"
echo "4. 退出"
echo ""

read -p "请输入选项 (1-4): " choice

case $choice in
    1)
        echo ""
        echo "=========================================="
        echo "小规模测试（2 篇）"
        echo "=========================================="
        echo ""
        echo "测试样本："
        echo "1. 股东会与董事会分权制度研究_许可.pdf（传统法学论证型，基线）"
        echo "2. 数字法学的理论表达_马长山.pdf（理论建构型，核心测试）"
        echo ""

        OUTPUT_DIR="results/v0.14-small-test-$(date +%Y%m%d-%H%M%S)"
        mkdir -p "$OUTPUT_DIR"

        echo "开始测试..."
        echo ""

        # 测试样本 1
        python scripts/run_v0.14_multi_model_test.py \
            --paper "raw/holdout-test/股东会与董事会分权制度研究_许可.pdf" \
            --output "$OUTPUT_DIR/sample1-许可.json"

        echo ""
        echo "样本 1 完成，继续样本 2..."
        echo ""

        # 测试样本 2
        python scripts/run_v0.14_multi_model_test.py \
            --paper "raw/holdout-test/数字法学的理论表达_马长山.pdf" \
            --output "$OUTPUT_DIR/sample2-马长山.json"

        echo ""
        echo "=========================================="
        echo "小规模测试完成"
        echo "=========================================="
        echo "结果保存在：$OUTPUT_DIR"
        ;;

    2)
        echo ""
        echo "=========================================="
        echo "完整测试（6 篇）"
        echo "=========================================="
        echo ""
        echo "测试样本："
        echo "1. 数字法学的理论表达_马长山.pdf"
        echo "2. 善终、凶死与杀人偿命_尚海明.pdf"
        echo "3. 股东会与董事会分权制度研究_许可.pdf"
        echo "4. 法典化时代的刑法典修订_周光权.pdf"
        echo "5. 迈向自主法学知识体系的比较法研究范式_宋亚辉.pdf"
        echo "6. 法秩序统一性原理之建构_雷磊.pdf"
        echo ""

        read -p "是否禁用 GPT 复核？(y/N): " disable_gpt

        if [[ "$disable_gpt" =~ ^[Yy]$ ]]; then
            GPT_FLAG="--no-gpt-review"
            echo "已禁用 GPT 复核"
        else
            GPT_FLAG=""
            echo "已启用 GPT 复核（默认 gpt-5.4，分歧时自动触发）"
        fi

        OUTPUT_DIR="results/v0.14-batch-test-$(date +%Y%m%d-%H%M%S)"

        echo ""
        echo "开始批量测试..."
        echo ""

        python scripts/run_v0.14_multi_model_test.py \
            --batch \
            --output-dir "$OUTPUT_DIR" \
            $GPT_FLAG

        echo ""
        echo "=========================================="
        echo "完整测试完成"
        echo "=========================================="
        echo "结果保存在：$OUTPUT_DIR"
        echo "汇总报告：$OUTPUT_DIR/summary.json"
        ;;

    3)
        echo ""
        echo "=========================================="
        echo "单篇测试"
        echo "=========================================="
        echo ""

        # 列出可用样本
        echo "可用样本："
        echo ""
        find raw/holdout-test raw/validation -name "*.pdf" -type f | nl
        echo ""

        read -p "请输入论文路径: " paper_path

        if [ ! -f "$paper_path" ]; then
            echo "错误：文件不存在：$paper_path"
            exit 1
        fi

        read -p "是否禁用 GPT 复核？(y/N): " disable_gpt

        if [[ "$disable_gpt" =~ ^[Yy]$ ]]; then
            GPT_FLAG="--no-gpt-review"
        else
            GPT_FLAG=""
        fi

        echo ""
        echo "开始测试..."
        echo ""

        python scripts/run_v0.14_multi_model_test.py \
            --paper "$paper_path" \
            $GPT_FLAG

        echo ""
        echo "=========================================="
        echo "单篇测试完成"
        echo "=========================================="
        ;;

    4)
        echo "退出"
        exit 0
        ;;

    *)
        echo "无效选项"
        exit 1
        ;;
esac

echo ""
echo "测试完成！"
echo ""
echo "下一步："
echo "1. 查看测试结果（JSON 文件）"
echo "2. 分析测试数据"
echo "3. 生成测试报告"
echo ""
