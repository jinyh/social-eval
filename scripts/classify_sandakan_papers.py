#!/usr/bin/env python3
"""
sandakan-new-metadata.csv 学科 Top-2 分类脚本

使用 qwen3.7-max (DashScope百炼) 对 1920 篇论文做学科分类，
输出主/次分类及概率。支持断点续跑。

用法: uv run python scripts/classify_sandakan_papers.py
"""

import asyncio
import csv
import json
import os
import sys
from pathlib import Path

import openai
from dotenv import load_dotenv

load_dotenv()

# ── 配置 ──
MODEL = "qwen3.7-max"
TEMPERATURE = 0.3
CONCURRENCY = 8
TIMEOUT = 60
MAX_RETRIES = 1

CSV_PATH = Path("results/sandakan-new-metadata.csv")
OUTPUT_PATH = Path("results/sandakan-ai-classification.json")

VALID_CATEGORIES = [
    "民商法学", "刑法学", "宪法学与行政法学", "诉讼法学", "法学理论",
    "环境与资源保护法学", "国际法学", "经济法学", "知识产权法学",
    "法律史", "党内法规学",
]

CATEGORY_LIST = "、".join(VALID_CATEGORIES)

PROMPT_TEMPLATE = """\
你是一位法学学科分类专家。根据论文标题和作者机构，判断该论文所属的法学二级学科。

可选学科（11个）：{categories}

## 分类规则

1. **劳动法、社会保障法方向**归入"民商法学"（非经济法学）。
2. **区分原则**：看论文的**核心贡献**属于哪个学科，而非标题中出现的背景领域。例如"生态环境损害赔偿的理论构成"的核心贡献是损害赔偿的私法构造（民商法学），而非环境保护（环境法学）。
3. **学科惯性原则**：论文的原始学科归属通常来自作者的学科定位和研究方向，除非标题有压倒性证据指向另一学科，否则不应轻易改变。标题中出现跨学科术语（如"行政违法性""数据爬取""跨法域"）往往只是研究背景，不代表核心贡献转移。

论文标题：{title}
作者机构：{institution}

返回 JSON（不要输出其他内容）：
{{"主分类": "学科名", "主分类概率": 0.xx, "次分类": "学科名", "次分类概率": 0.xx}}

要求：
- 主分类概率 + 次分类概率 ≤ 1.0
- 主分类概率 > 次分类概率
- 概率反映你对分类确定性的判断（越确定越高）
- 主分类和次分类必须从上述11个学科中选择
"""


def load_csv() -> list[dict]:
    """读取 CSV，返回论文列表。"""
    with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_existing_results() -> dict[int, dict]:
    """加载已有的分类结果（断点续跑）。"""
    if not OUTPUT_PATH.exists():
        return {}
    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {int(k): v for k, v in data.items()}


def save_results(results: dict[int, dict]):
    """保存分类结果到 JSON。"""
    serializable = {str(k): v for k, v in results.items()}
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)


def extract_json(text: str) -> dict:
    """从 LLM 输出中提取 JSON。"""
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 尝试从 markdown 代码块提取
    if "```" in text:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    # 尝试找最外层 {}
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"无法解析 JSON: {text[:200]}")


def validate_result(result: dict) -> dict:
    """校验并修正 LLM 输出。"""
    # 检查必需字段
    for key in ("主分类", "主分类概率", "次分类", "次分类概率"):
        if key not in result:
            raise ValueError(f"缺少字段: {key}")

    # 分类映射: 劳动法与社会保障法学 → 民商法学
    mapping = {"劳动法与社会保障法学": "民商法学"}
    result["主分类"] = mapping.get(result["主分类"], result["主分类"])
    result["次分类"] = mapping.get(result["次分类"], result["次分类"])

    # 校验分类是否在有效列表中
    if result["主分类"] not in VALID_CATEGORIES:
        raise ValueError(f"无效主分类: {result['主分类']}")
    if result["次分类"] not in VALID_CATEGORIES:
        raise ValueError(f"无效次分类: {result['次分类']}")

    # 校验概率
    p1 = float(result["主分类概率"])
    p2 = float(result["次分类概率"])
    p1 = max(0.50, min(0.95, p1))
    p2 = max(0.00, min(0.40, p2))
    if p1 + p2 > 1.0:
        scale = 1.0 / (p1 + p2) * 0.98
        p1 *= scale
        p2 *= scale
    if p1 <= p2:
        p1, p2 = p1, p2 * 0.5

    result["主分类概率"] = round(p1, 3)
    result["次分类概率"] = round(p2, 3)
    return result


async def classify_one(
    client: openai.AsyncOpenAI,
    pid: int,
    title: str,
    institution: str,
    semaphore: asyncio.Semaphore,
) -> dict | None:
    """对单篇论文调用 LLM 分类。"""
    prompt = PROMPT_TEMPLATE.format(
        categories=CATEGORY_LIST,
        title=title,
        institution=institution,
    )

    async with semaphore:
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=MODEL,
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"},
                        temperature=TEMPERATURE,
                    ),
                    timeout=TIMEOUT,
                )
                content = response.choices[0].message.content
                result = extract_json(content)
                result = validate_result(result)
                result["pid"] = pid
                result["title"] = title
                return result

            except Exception as e:
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(2)
                    continue
                print(f"  ❌ PID {pid} 失败 ({title[:20]}...): {e}", flush=True)
                return None


async def main():
    papers = load_csv()
    existing = load_existing_results()
    print(f"共 {len(papers)} 篇论文，已完成 {len(existing)} 篇", flush=True)

    # 过滤待处理
    todo = [p for p in papers if int(p["编号"]) not in existing]
    print(f"待处理: {len(todo)} 篇", flush=True)

    if not todo:
        print("全部完成，无需处理。")
        return

    client = openai.AsyncOpenAI(
        api_key=os.getenv("DASHSCOPE_API_KEY", ""),
        base_url=os.getenv(
            "DASHSCOPE_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
    )

    semaphore = asyncio.Semaphore(CONCURRENCY)
    results = dict(existing)
    completed = 0
    failed = 0
    save_counter = 0

    async def process_and_save(paper):
        nonlocal completed, failed, save_counter
        r = await classify_one(
            client,
            int(paper["编号"]),
            paper["题目"],
            paper["作者机构"],
            semaphore,
        )
        if r is not None:
            pid = r.pop("pid")
            r.pop("title", None)
            results[pid] = r
            completed += 1
        else:
            failed += 1
        save_counter += 1
        # 每 20 条保存一次
        if save_counter % 20 == 0:
            save_results(results)
            print(
                f"  进度: {len(results)}/{len(papers)} (+{completed} -{failed})",
                flush=True,
            )

    # 逐条提交，信号量控制并发
    tasks = [asyncio.create_task(process_and_save(p)) for p in todo]
    await asyncio.gather(*tasks)

    # 最终保存
    save_results(results)

    # 最终统计
    print(f"\n完成: {len(results)}/{len(papers)}")
    print(f"结果已保存到: {OUTPUT_PATH}")

    # 分布统计
    from collections import Counter
    main_dist = Counter(v["主分类"] for v in results.values())
    print("\n主分类分布:")
    for cls, cnt in main_dist.most_common():
        print(f"  {cls:20s} {cnt:4d} ({cnt/len(results)*100:.1f}%)")

    avg_p1 = sum(v["主分类概率"] for v in results.values()) / len(results)
    avg_p2 = sum(v["次分类概率"] for v in results.values()) / len(results)
    print(f"\n平均概率: 主={avg_p1:.3f}, 次={avg_p2:.3f}, 和={avg_p1+avg_p2:.3f}")


if __name__ == "__main__":
    asyncio.run(main())
