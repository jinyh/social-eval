#!/usr/bin/env python3
"""学术月刊论文学科分类脚本

使用 Qwen、GLM、DeepSeek、Kimi 四个模型逐篇分类到教育部法学 12 个二级学科。
结果写入 97001X_学术月刊_法学院2015起.csv 的 5 个新列。

用法：
    # 全量执行
    uv run python scripts/classify_xueshuyuekan.py

    # 只跑前 N 篇（测试）
    uv run python scripts/classify_xueshuyuekan.py --limit 3

    # 强制重跑（忽略进度文件）
    uv run python scripts/classify_xueshuyuekan.py --force
"""

import argparse
import asyncio
import csv
import glob
import json
import logging
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import openai

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import settings

# === 配置 ===

CSV_PATH = PROJECT_ROOT / "raw/xueshuyuekan/97001X_学术月刊_法学院2015起.csv"
MD_DIR = PROJECT_ROOT / "raw/xueshuyuekan"
PROGRESS_PATH = PROJECT_ROOT / "results/runs/xueshuyuekan-classify/progress.json"
MAX_CONTENT_CHARS = 12000  # 正文截断长度

# 四个模型及其对应的分类列后缀
MODELS = {
    "qwen3.6-plus": "Q",
    "glm-5.1": "G",
    "deepseek-v4-pro": "D",
    "kimi-k2.6": "K",
}

# 教育部法学 12 个二级学科
CATEGORIES = [
    ("法学理论", "法理学、法哲学、法社会学、比较法学等基础理论研究"),
    ("法律史", "中国法制史、外国法制史、法律思想史"),
    ("宪法学与行政法学", "宪法、行政法、行政诉讼法相关研究"),
    ("刑法学", "犯罪学、刑罚学、刑事政策"),
    ("民商法学", "民法、商法、民事诉讼法中的实体法问题"),
    ("诉讼法学", "刑事诉讼法、民事诉讼法、行政诉讼法的程序法研究"),
    ("经济法学", "经济法、竞争法、金融法、财税法"),
    ("环境与资源保护法学", "环境法、自然资源法、能源法"),
    ("国际法学", "国际公法、国际私法、国际经济法"),
    ("知识产权法学", "著作权法、专利法、商标法"),
    ("党内法规学", "党内法规制度建设、党规与国法关系"),
    ("数字法学", "人工智能法律规制、数据法学、网络法学、算法治理"),
]

VALID_CATEGORIES = {c[0] for c in CATEGORIES}

# 并发控制
PAPER_CONCURRENCY = 5  # 同时处理的论文数


# === Prompt ===

def build_prompt(title: str, keywords: str, abstract: str, content: str) -> str:
    """构造分类 prompt"""
    cat_list = "\n".join(
        f"{i+1}. {name} — {desc}" for i, (name, desc) in enumerate(CATEGORIES)
    )

    return f"""你是一位法学学科分类专家。请阅读以下法学论文，将其归入教育部法学二级分类的 12 个子学科之一。

## 12 个子学科
{cat_list}

## 论文信息
- 标题：{title}
- 关键词：{keywords}
- 摘要：{abstract}
- 正文（截取前 {MAX_CONTENT_CHARS} 字符）：
{content}

## 输出要求
以 JSON 格式输出，包含：
- "category"：子学科名称（必须是上述 12 个之一，精确匹配，不要自创类别）
- "confidence"：置信度（0-1 之间的数字）
- "reason"：分类理由（50 字以内）

只输出 JSON，不要输出其他内容。"""


# === API 调用 ===

async def call_model(client: openai.AsyncOpenAI, model: str, prompt: str) -> dict:
    """调用单个模型，返回解析后的分类结果"""
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.3,
            ),
            timeout=180,
        )
        content = response.choices[0].message.content
        if not content:
            return {"category": "", "confidence": 0, "reason": "空响应", "error": "empty"}

        # 提取 JSON
        result = _extract_json(content)
        if result is None:
            return {"category": "", "confidence": 0, "reason": "", "error": f"JSON 解析失败: {content[:100]}"}

        # 校验 category 是否在合法范围内
        cat = result.get("category", "").strip()
        if cat not in VALID_CATEGORIES:
            # 尝试模糊匹配
            matched = _fuzzy_match_category(cat)
            if matched:
                result["_original_category"] = cat
                result["category"] = matched
            else:
                result["error"] = f"无效分类: {cat}"
                result["category"] = ""

        return result

    except asyncio.TimeoutError:
        return {"category": "", "confidence": 0, "reason": "", "error": "超时"}
    except Exception as e:
        return {"category": "", "confidence": 0, "reason": "", "error": str(e)[:200]}


def _extract_json(text: str) -> dict | None:
    """从模型输出中提取 JSON"""
    import re

    # 尝试 ```json ... ```
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试 ``` ... ```
    match = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        candidate = match.group(1)
        if candidate.startswith("{"):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

    # 直接找 { ... }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None


def _fuzzy_match_category(cat: str) -> str | None:
    """模糊匹配分类名称"""
    if not cat:
        return None
    # 常见变体映射
    aliases = {
        "法理学": "法学理论",
        "宪法学": "宪法学与行政法学",
        "行政法学": "宪法学与行政法学",
        "民商法": "民商法学",
        "商法学": "民商法学",
        "民法学": "民商法学",
        "环境法学": "环境与资源保护法学",
        "环境法": "环境与资源保护法学",
        "国际法": "国际法学",
        "知识产权法": "知识产权法学",
        "经济法": "经济法学",
        "刑法": "刑法学",
        "诉讼法": "诉讼法学",
        "法律史学": "法律史",
        "法制史": "法律史",
        "数字法": "数字法学",
    }
    return aliases.get(cat)


# === 文件处理 ===

def find_md_file(lngid: str) -> str | None:
    """根据 lngid 查找对应的 md 文件"""
    pattern = str(MD_DIR / f"{lngid}_*.md")
    matches = glob.glob(pattern)
    if matches:
        return matches[0]
    return None


def read_md_content(md_path: str, max_chars: int = MAX_CONTENT_CHARS) -> str:
    """读取 md 文件内容并截断"""
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()
    if len(content) > max_chars:
        content = content[:max_chars] + "\n...[内容已截断]"
    return content


# === 进度管理 ===

def load_progress() -> dict:
    """加载进度文件"""
    if PROGRESS_PATH.exists():
        with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"completed": {}, "errors": []}


def save_progress(progress: dict):
    """保存进度文件"""
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


# === 主流程 ===

async def classify_paper(
    client: openai.AsyncOpenAI,
    row: dict,
    semaphore: asyncio.Semaphore,
    progress: dict,
) -> dict:
    """对单篇论文进行四模型分类"""
    lngid = row.get("lngid", "")
    title = row.get("titlec", "")
    keywords = row.get("keywordc", "")
    abstract = row.get("remarkc", "")

    # 检查是否已完成
    if lngid in progress["completed"]:
        return progress["completed"][lngid]

    async with semaphore:
        # 查找 md 文件
        md_path = find_md_file(lngid)
        if not md_path:
            logging.warning(f"[{lngid}] 未找到 md 文件: {title[:30]}")
            result = {"error": "未找到 md 文件"}
            progress["errors"].append({"lngid": lngid, "error": "未找到 md 文件"})
            return result

        # 读取内容
        content = read_md_content(md_path)

        # 构造 prompt
        prompt = build_prompt(title, keywords, abstract, content)

        # 并发调用 4 个模型
        tasks = {}
        for model_name, suffix in MODELS.items():
            tasks[suffix] = asyncio.create_task(
                call_model(client, model_name, prompt)
            )

        # 等待所有模型完成
        results = {}
        for suffix, task in tasks.items():
            try:
                results[suffix] = await task
            except Exception as e:
                results[suffix] = {"category": "", "confidence": 0, "reason": "", "error": str(e)[:200]}

        # 保存结果
        paper_result = {
            "lngid": lngid,
            "title": title[:50],
            "timestamp": datetime.now().isoformat(),
            "results": results,
        }

        progress["completed"][lngid] = paper_result
        save_progress(progress)

        # 日志
        cats = {s: r.get("category", "?") for s, r in results.items()}
        errors = [s for s, r in results.items() if r.get("error")]
        if errors:
            logging.warning(f"[{lngid}] {title[:30]} → {cats} (错误: {errors})")
        else:
            logging.info(f"[{lngid}] {title[:30]} → {cats}")

        return paper_result


def majority_vote(results: dict) -> str:
    """多数投票决定最终分类"""
    cats = []
    for suffix, r in results.items():
        cat = r.get("category", "").strip()
        if cat and cat in VALID_CATEGORIES:
            cats.append(cat)

    if not cats:
        return ""

    counter = Counter(cats)
    most_common = counter.most_common(1)
    return most_common[0][0] if most_common else ""


def write_results_to_csv(csv_path: Path, progress: dict):
    """将分类结果写回 CSV"""
    # 读取原始 CSV
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        original_fieldnames = list(reader.fieldnames)
        rows = list(reader)

    # 添加新列
    new_cols = ["分类-Q", "分类-G", "分类-D", "分类-K", "分类"]
    fieldnames = original_fieldnames + [c for c in new_cols if c not in original_fieldnames]

    # 填充分类结果
    completed = progress.get("completed", {})
    for row in rows:
        lngid = row.get("lngid", "")
        paper_result = completed.get(lngid)

        if paper_result and "results" in paper_result:
            results = paper_result["results"]
            row["分类-Q"] = results.get("Q", {}).get("category", "")
            row["分类-G"] = results.get("G", {}).get("category", "")
            row["分类-D"] = results.get("D", {}).get("category", "")
            row["分类-K"] = results.get("K", {}).get("category", "")
            row["分类"] = majority_vote(results)
        else:
            for col in new_cols:
                row.setdefault(col, "")

    # 写回 CSV
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    logging.info(f"已写入 {csv_path}，共 {len(rows)} 行，新增列: {new_cols}")


async def main():
    parser = argparse.ArgumentParser(description="学术月刊论文学科分类")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 篇（0=全部）")
    parser.add_argument("--force", action="store_true", help="忽略进度文件，强制重跑")
    args = parser.parse_args()

    # 配置日志
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                PROJECT_ROOT / "results/runs/xueshuyuekan-classify/execution.log",
                encoding="utf-8",
            ),
        ],
    )
    logger = logging.getLogger(__name__)

    # 读取 CSV
    logger.info(f"读取 CSV: {CSV_PATH}")
    with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    logger.info(f"  共 {len(rows)} 篇论文")

    if args.limit > 0:
        rows = rows[:args.limit]
        logger.info(f"  限制处理前 {args.limit} 篇")

    # 加载进度
    progress = {"completed": {}, "errors": []} if args.force else load_progress()
    if "completed" not in progress:
        progress["completed"] = {}
    if "errors" not in progress:
        progress["errors"] = []
    already_done = len(progress.get("completed", {}))
    if already_done > 0:
        logger.info(f"  已完成 {already_done} 篇，继续处理剩余论文")

    # 初始化 DashScope 客户端
    client = openai.AsyncOpenAI(
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
    )

    # 并发控制
    semaphore = asyncio.Semaphore(PAPER_CONCURRENCY)

    # 逐篇分类
    start_time = time.time()
    tasks = [classify_paper(client, row, semaphore, progress) for row in rows]
    await asyncio.gather(*tasks)

    elapsed = time.time() - start_time
    logger.info(f"分类完成，耗时 {elapsed:.1f}s")

    # 写回 CSV
    write_results_to_csv(CSV_PATH, progress)

    # 统计
    completed = progress.get("completed", {})
    all_cats = []
    model_cats = {"Q": [], "G": [], "D": [], "K": []}

    for lngid, paper_result in completed.items():
        results = paper_result.get("results", {})
        votes = []
        for suffix in ["Q", "G", "D", "K"]:
            cat = results.get(suffix, {}).get("category", "")
            model_cats[suffix].append(cat)
            if cat:
                votes.append(cat)
        if votes:
            all_cats.append(Counter(votes).most_common(1)[0][0])

    logger.info(f"\n=== 分类统计 ===")
    logger.info(f"总完成: {len(completed)} 篇")

    # 一致性
    agree_count = 0
    for i in range(len(all_cats)):
        cats = [model_cats[s][i] for s in ["Q", "G", "D", "K"] if i < len(model_cats[s])]
        if len(set(cats)) == 1 and cats[0]:
            agree_count += 1
    logger.info(f"4 模型一致: {agree_count}/{len(all_cats)} ({agree_count/max(len(all_cats),1)*100:.1f}%)")

    # 分布
    dist = Counter(all_cats)
    logger.info(f"分类分布:")
    for cat, cnt in dist.most_common():
        logger.info(f"  {cat}: {cnt}")

    # 错误统计
    error_count = 0
    for lngid, paper_result in completed.items():
        results = paper_result.get("results", {})
        for suffix, r in results.items():
            if r.get("error"):
                error_count += 1
    if error_count > 0:
        logger.info(f"模型调用错误: {error_count} 次")


if __name__ == "__main__":
    asyncio.run(main())
