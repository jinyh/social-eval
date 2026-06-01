#!/bin/bash
# Holdout 验证：v2.56.1 在 4 篇未见过的论文上测试

set -e

echo "=== Holdout 验证 v2.56.1 ==="
echo "测试论文：holdout-test 目录下的 4 篇"
echo "模型：4 个（deepseek-v4-pro, glm-5.1, kimi-k2.6, qwen3.6-plus）"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# 创建输出目录
OUTPUT_DIR="results/v2.56.1-holdout-test"
mkdir -p "$OUTPUT_DIR"

# 获取 holdout-test 中的论文
PAPERS=(
    "raw/holdout-test/股东会与董事会分权制度研究_许可.pdf"
    "raw/holdout-test/数字法学的理论表达_马长山.pdf"
    "raw/holdout-test/善终、凶死与杀人偿命——中国人死刑观念的文化阐释_尚海明.pdf"
    "raw/holdout-test/法典化时代的刑法典修订_周光权.pdf"
)

echo "开始测试 ${#PAPERS[@]} 篇论文..."

# 使用 Python 脚本评估
.venv/bin/python << 'PYEOF'
import asyncio
import json
import sys
import statistics
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path.cwd()))

from src.evaluation.providers.factory import create_providers
from src.ingestion.preprocessor import process_file
from src.knowledge.loader import _normalize_framework_data
from src.knowledge.schemas import Framework
import yaml

FRAMEWORK_PATH = "configs/frameworks/law-v2.56-prompt-aligned.yaml"
PAPERS = [
    "raw/holdout-test/股东会与董事会分权制度研究_许可.pdf",
    "raw/holdout-test/数字法学的理论表达_马长山.pdf",
    "raw/holdout-test/善终、凶死与杀人偿命——中国人死刑观念的文化阐释_尚海明.pdf",
    "raw/holdout-test/法典化时代的刑法典修订_周光权.pdf"
]
MODELS = ["deepseek-v4-pro", "glm-5.1", "kimi-k2.6", "qwen3.6-plus"]
OUTPUT_DIR = Path("results/v2.56.1-holdout-test")

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
    
    print(f"\n=== {Path(paper_path).stem} ===")
    paper = process_file(paper_path)
    dimensions = framework.dimensions
    
    dimension_results = {}
    
    for dim in dimensions:
        prompt = build_prompt(dim, paper)
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
        
        scores_str = ", ".join(f"{k}={v}" for k, v in aggregated["model_scores"].items())
        print(f"  {dim.name_zh}: {scores_str} | std={aggregated['std']:.1f}")
    
    return {
        "paper": paper_path,
        "dimension_results": dimension_results
    }

async def main():
    print("加载框架...")
    framework = load_framework(FRAMEWORK_PATH)
    
    print("创建 providers...")
    providers = create_providers(MODELS)
    semaphore = asyncio.Semaphore(10)
    
    print("开始评估...")
    all_results = await asyncio.gather(
        *[evaluate_paper(framework, providers, paper, semaphore) for paper in PAPERS]
    )
    
    # 保存结果
    output_file = OUTPUT_DIR / f"holdout_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    print(f"\n结果已保存：{output_file}")
    
    # 分析结果
    all_stds = []
    for paper_result in all_results:
        for dim_data in paper_result['dimension_results'].values():
            all_stds.append(dim_data['std'])
    
    avg_std = statistics.mean(all_stds)
    print(f"\n平均 std: {avg_std:.2f}")
    print(f"std > 8 的比例: {sum(1 for s in all_stds if s > 8)}/{len(all_stds)}")

if __name__ == "__main__":
    asyncio.run(main())
PYEOF

echo ""
echo "=== Holdout 验证完成 ==="
