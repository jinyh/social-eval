#!/bin/bash
# 快速验证脚本 - v2.56 版本
# 使用单篇论文，4 个模型，单次评估（约 3-5 分钟）

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 使用虚拟环境的 Python
PYTHON="$PROJECT_ROOT/.venv/bin/python"

# 默认参数
FRAMEWORK="${1:-configs/frameworks/law-v2.56-prompt-aligned.yaml}"
PAPER="${2:-raw/calibration-regression/司法公正与同理心正义_杜宴林.pdf}"
OUTPUT_DIR="results/autoresearch/v2.56"

# 创建输出目录
mkdir -p "$OUTPUT_DIR"

# 生成时间戳
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTPUT_FILE="$OUTPUT_DIR/quick-verify-$TIMESTAMP.json"

echo "=== 快速验证 v2.56 ==="
echo "框架: $FRAMEWORK"
echo "论文: $PAPER"
echo "输出: $OUTPUT_FILE"
echo ""

# 运行单次评估（4 个模型）
cd "$PROJECT_ROOT"
$PYTHON << 'PYEOF'
import asyncio
import json
import sys
import statistics
from pathlib import Path
from datetime import datetime

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent if '__file__' in globals() else Path.cwd()
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.providers.factory import create_providers
from src.ingestion.preprocessor import process_file
from src.knowledge.loader import _normalize_framework_data
from src.knowledge.schemas import Framework
import yaml

# 参数
FRAMEWORK_PATH = sys.argv[1] if len(sys.argv) > 1 else "configs/frameworks/law-v2.56-prompt-aligned.yaml"
PAPER_PATH = sys.argv[2] if len(sys.argv) > 2 else "raw/calibration-regression/司法公正与同理心正义_杜宴林.pdf"
OUTPUT_FILE = sys.argv[3] if len(sys.argv) > 3 else f"results/autoresearch/v2.56/quick-verify-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"

MODELS = ["deepseek-v4-pro", "glm-5.1", "kimi-k2.6", "qwen3.6-plus"]

def load_framework(path: str) -> Framework:
    with open(path, 'r', encoding='utf-8') as f:
        raw = yaml.safe_load(f)
    normalized = _normalize_framework_data(raw)
    return Framework(**normalized)

async def _call_provider(provider, prompt: str, semaphore):
    async with semaphore:
        try:
            start = asyncio.get_event_loop().time()
            raw = await provider.generate_json_response(prompt)
            elapsed = asyncio.get_event_loop().time() - start
            return (raw, None, elapsed)
        except Exception as e:
            return (None, str(e), 0.0)

def aggregate_scores(scores: dict) -> dict:
    if not scores:
        return {"mean": 0.0, "std": 0.0, "model_scores": {}}
    values = list(scores.values())
    mean = statistics.mean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    return {"mean": round(mean, 1), "std": round(std, 1), "model_scores": scores}

async def evaluate_paper(framework, providers, paper_path, semaphore):
    from src.evaluation.prompt_builder import build_prompt

    paper = process_file(paper_path)
    dimensions = framework.dimensions

    dimension_results = {}

    for dim in dimensions:
        prompt = build_prompt(dim, paper)

        # 并发调用所有模型
        results = await asyncio.gather(
            *[_call_provider(p, prompt, semaphore) for p in providers],
            return_exceptions=False,
        )

        scores = {}
        for (raw, error, elapsed), provider in zip(results, providers):
            if error:
                continue
            if isinstance(raw, dict):
                score = raw.get("score")
                if score is not None:
                    scores[provider.model_name] = int(score)

        aggregated = aggregate_scores(scores)
        dimension_results[dim.key] = aggregated

    return dimension_results

async def main():
    print(f"加载框架: {FRAMEWORK_PATH}")
    framework = load_framework(FRAMEWORK_PATH)

    print(f"加载论文: {PAPER_PATH}")

    print(f"创建 providers: {MODELS}")
    providers = create_providers(MODELS)
    semaphore = asyncio.Semaphore(10)

    print("开始评估...")
    dimension_results = await evaluate_paper(framework, providers, PAPER_PATH, semaphore)

    # 计算整体指标
    all_stds = [dim_data['std'] for dim_data in dimension_results.values()]
    avg_std = statistics.mean(all_stds)
    high_confidence_count = sum(1 for std in all_stds if std <= 5.0)
    high_confidence_ratio = high_confidence_count / len(all_stds)
    composite_score = -avg_std + 10 * high_confidence_ratio

    result = {
        "framework": FRAMEWORK_PATH,
        "paper": PAPER_PATH,
        "models": MODELS,
        "timestamp": datetime.now().isoformat(),
        "dimensions": dimension_results,
        "overall": {
            "avg_std": round(avg_std, 2),
            "high_confidence_count": high_confidence_count,
            "high_confidence_ratio": round(high_confidence_ratio, 3),
            "composite_score": round(composite_score, 2)
        }
    }

    # 保存结果
    Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存: {OUTPUT_FILE}")
    print(f"平均 std: {avg_std:.2f}")
    print(f"高置信度比例: {high_confidence_ratio:.1%}")
    print(f"Composite Score: {composite_score:.2f}")

    return composite_score

if __name__ == "__main__":
    asyncio.run(main())
PYEOF

echo ""
echo "=== 验证完成 ==="
