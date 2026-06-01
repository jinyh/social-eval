#!/usr/bin/env python3
"""
Top 30 论文 × 树状知识库匹配分析（优化版 v2）

优化策略：
1. 标识性概念：关键词匹配（主）+ 语义匹配（辅），过滤通用词
2. 原创性理论：语义匹配（主）+ LLM验证（必需），捕获简称
3. 框架结构：语义匹配（括号内容）+ LLM推理（必需）

方法：差异化关键词生成 + 语义匹配（embedding）+ LLM 语义验证
"""

import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import fitz  # PyMuPDF
import numpy as np
import openai
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# ── 路径配置 ──────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_MD = PROJECT_ROOT / "knowledge" / "中国法学自主知识体系-树状知识库.md"
PAPER_DIR = PROJECT_ROOT / "raw" / "top30_paper"
OUTPUT_CSV = PROJECT_ROOT / "results" / "top30-knowledge-matching-v2.csv"
CACHE_DIR = PROJECT_ROOT / ".cache" / "embeddings"

# ── LLM 配置（DashScope 兼容 OpenAI API） ────────────────

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL_NAME = "qwen3.6-plus"
TEMPERATURE = 0.3
MAX_TOKENS = 4096

# ── 语义匹配配置 ──────────────────────────────────────────

EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# 差异化相似度阈值
SEMANTIC_THRESHOLDS = {
    "标识性概念": 0.72,  # 较严格
    "原创性理论": 0.68,  # 略宽松（捕获简称）
    "框架结构": 0.65,    # 最宽松（高度抽象）
}

# 通用词黑名单
GENERIC_BLACKLIST = {
    "法", "礼", "刑",  # 1字符
    "法律", "法理", "政理", "法治", "政法",  # 2字符通用词
    "行政法", "经济法", "社会法", "刑法", "民法",  # 学科名称
}

# 如果环境变量为空，尝试从 .env 文件读取
if not DASHSCOPE_API_KEY:
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DASHSCOPE_API_KEY=") and not line.startswith("#"):
                DASHSCOPE_API_KEY = line.split("=", 1)[1].strip()
                break


# ═══════════════════════════════════════════════════════════
# 阶段 1：解析知识库（增强版）
# ═══════════════════════════════════════════════════════════

def parse_knowledge_base(md_path: Path) -> dict:
    """
    解析树状知识库 MD 文件，返回结构化数据。

    返回格式：
    {
        "d01_法理学": {
            "标识性概念": ["法律", "法理", ...],
            "原创性理论": ["中国特色社会主义法治体系理论", ...],
            "框架结构": ["本体论（法的存在及其本质）", ...]
        },
        ...
    }
    """
    text = md_path.read_text(encoding="utf-8")

    knowledge = {}
    discipline_pattern = re.compile(
        r"[├└]──\s*(\d+)\.\s*(.+?)自主知识体系\s*〔(d\d+)〕"
    )

    # 提取所有学科及其行号
    disciplines = []
    for i, line in enumerate(text.splitlines()):
        m = discipline_pattern.search(line)
        if m:
            num = m.group(1)
            name = m.group(2).strip()
            code = m.group(3)
            disciplines.append({
                "num": num,
                "name": name,
                "code": code,
                "line": i,
                "key": f"{code}_{name}"
            })

    # 提取灵魂篇
    soul_match = re.search(r"[├└]──\s*★\s*灵魂[：:](.+)", text)
    if soul_match:
        disciplines.insert(0, {
            "num": "0",
            "name": "习近平法治思想",
            "code": "d00",
            "line": -1,
            "key": "d00_习近平法治思想"
        })

    lines = text.splitlines()

    for idx, disc in enumerate(disciplines):
        start_line = disc["line"]
        if idx + 1 < len(disciplines):
            end_line = disciplines[idx + 1]["line"]
        else:
            end_line = len(lines)

        section_lines = lines[max(0, start_line):end_line]

        entry = {
            "标识性概念": [],
            "原创性理论": [],
            "框架结构": [],
        }

        current_section = None
        for sline in section_lines:
            if re.search(r"二、标识性概念", sline):
                current_section = "标识性概念"
                continue
            elif re.search(r"三、原创性理论", sline):
                current_section = "原创性理论"
                continue
            elif re.search(r"四、框架结构", sline):
                current_section = "框架结构"
                continue
            elif re.search(r"[一二三四五六七八九十]、(?!标识性概念|原创性理论|框架结构)", sline):
                if current_section and not re.search(r"(标识性概念|原创性理论|框架结构)", sline):
                    pass

            if current_section is None:
                continue

            # 匹配条目
            item_match = re.search(r"[├└]──\s*(?:\d+\.\s*|\(\S+?\)\s*)?(.+)", sline)
            if item_match:
                item_text = item_match.group(1).strip()
                if item_text and not item_text.startswith("├") and not item_text.startswith("└"):
                    entry[current_section].append(item_text)

        knowledge[disc["key"]] = entry

    return knowledge


def _generate_keywords(item: str, category: str) -> list:
    """
    根据类别生成不同的关键词(差异化策略)

    - 标识性概念: 3-8字符, 过滤通用词
    - 原创性理论: 提取核心词(去掉"理论"/"论"后缀)
    - 框架结构: 提取括号内关键词
    """
    keywords = set()
    clean = re.sub(r"[（(].+?[）)]", "", item).strip()

    # 过滤通用词
    if len(clean) <= 2 or clean in GENERIC_BLACKLIST:
        return []

    if category == "标识性概念":
        # 3-8字符适合关键词匹配
        if 3 <= len(clean) <= 8:
            keywords.add(clean)
            # 去掉引号
            quote_chars = '“”「」『』'
            unquoted = clean.strip(quote_chars)
            if len(unquoted) >= 3:
                keywords.add(unquoted)

    elif category == "原创性理论":
        # 提取核心词（去掉"理论"/"论"后缀）
        keywords.add(clean)
        for suffix in ["理论", "论"]:
            if clean.endswith(suffix) and len(clean) > len(suffix) + 2:
                core = clean[:-len(suffix)]
                if len(core) >= 3:
                    keywords.add(core)

    elif category == "框架结构":
        # 提取括号内的关键词
        paren_match = re.search(r"[（(](.+?)[）)]", item)
        if paren_match:
            paren_content = paren_match.group(1)
            # 分割多个关键词
            for part in re.split(r"[、，,；]", paren_content):
                part = part.strip()
                if len(part) >= 3:
                    keywords.add(part)
        # 也保留主体部分（去掉括号和编号）
        main = re.sub(r"[（(].+?[）)]", "", item)
        main = re.sub(r"^[第\\d一二三四五六七八九十]+[部分：、]*", "", main)
        main = re.sub(r"^\([一二三四五六七八九十\\d]+\)\s*", "", main)
        main = main.strip()
        if len(main) >= 3:
            keywords.add(main)

    return [kw for kw in keywords if len(kw) >= 3]


def build_keyword_index(knowledge: dict) -> dict:
    """
    为每个知识库条目生成匹配关键词(差异化策略)
    返回 {keyword: [(discipline, category, item), ...]}
    """
    index = {}

    for disc_key, sections in knowledge.items():
        for category, items in sections.items():
            for item in items:
                keywords = _generate_keywords(item, category)
                for kw in keywords:
                    if kw not in index:
                        index[kw] = []
                    index[kw].append((disc_key, category, item))

    return index


# ═══════════════════════════════════════════════════════════
# 阶段 1.5：构建语义匹配索引（差异化策略）
# ═══════════════════════════════════════════════════════════

def build_semantic_index(
    knowledge: dict,
    model: SentenceTransformer,
    cache_path: Path = None
) -> Tuple[List[Tuple], np.ndarray]:
    """
    为知识库条目构建 embedding 索引(差异化策略)

    - 标识性概念: 只对5+字符做语义匹配
    - 原创性理论: 全部做语义匹配
    - 框架结构: 使用括号内容做语义匹配

    返回:
    - items: [(disc_key, category, item), ...]
    - embeddings: numpy array
    """
    if cache_path and cache_path.exists():
        print(f"   从缓存加载 embedding：{cache_path}")
        data = np.load(cache_path, allow_pickle=True)
        return data['items'].tolist(), data['embeddings']

    items = []
    texts = []

    for disc_key, sections in knowledge.items():
        for category in ["标识性概念", "原创性理论", "框架结构"]:
            for item in sections.get(category, []):
                # 标识性概念：只对5+字符做语义匹配
                if category == "标识性概念" and len(item) < 5:
                    continue

                # 框架结构：使用括号内容
                if category == "框架结构":
                    paren_match = re.search(r"[（(](.+?)[）)]", item)
                    if paren_match:
                        text = paren_match.group(1)
                    else:
                        # 去掉编号
                        text = re.sub(r"^[第\d一二三四五六七八九十]+[部分：、]*", "", item)
                        text = re.sub(r"^\([一二三四五六七八九十\d]+\)\s*", "", text)
                else:
                    text = item

                items.append((disc_key, category, item))
                texts.append(text)

    print(f"   计算 {len(texts)} 个条目的 embedding...")
    embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cache_path, items=np.array(items, dtype=object), embeddings=embeddings)
        print(f"   embedding 已缓存到：{cache_path}")

    return items, embeddings


def semantic_match(
    paper_text: str,
    items: List[Tuple],
    embeddings: np.ndarray,
    model: SentenceTransformer,
    top_k: int = 30
) -> Dict[str, Dict[str, List[Tuple]]]:
    """
    使用 embedding 做语义匹配(差异化阈值)

    返回:
    {
        "d11_刑法学": {
            "标识性概念": [("正当防卫", 0.85), ...],
            "原创性理论": [("社会危害性理论", 0.78), ...],
            "框架结构": [("本体论(法的存在及其本质)", 0.70), ...]
        },
        ...
    }
    """
    # 按段落切分
    paragraphs = [p.strip() for p in paper_text.split('\n\n') if len(p.strip()) > 50]

    if not paragraphs:
        return {}

    # 计算段落 embedding
    para_embeddings = model.encode(paragraphs, show_progress_bar=False, convert_to_numpy=True)

    # 计算相似度矩阵
    similarities = cosine_similarity(para_embeddings, embeddings)
    max_similarities = similarities.max(axis=0)

    # 按类别筛选（差异化阈值）
    matches = []
    for idx, sim in enumerate(max_similarities):
        disc_key, category, item = items[idx]
        threshold = SEMANTIC_THRESHOLDS.get(category, 0.70)

        if sim >= threshold:
            matches.append((disc_key, category, item, sim))

    # 按相似度排序，取 top_k
    matches = sorted(matches, key=lambda x: x[3], reverse=True)[:top_k]

    # 组织成字典格式
    result = {}
    for disc_key, category, item, sim in matches:
        if disc_key not in result:
            result[disc_key] = {"标识性概念": [], "原创性理论": [], "框架结构": []}
        result[disc_key][category].append((item, sim))

    return result


# ═══════════════════════════════════════════════════════════
# 阶段 2：PDF 文本提取
# ═══════════════════════════════════════════════════════════

def parse_paper_filename(filename: str) -> dict:
    """从文件名解析论文元数据"""
    stem = Path(filename).stem
    parts = stem.split("-")

    if len(parts) < 7:
        return {
            "编号": parts[0] if parts else "",
            "期刊": parts[1] if len(parts) > 1 else "",
            "年份": parts[2] if len(parts) > 2 else "",
            "期": parts[3] if len(parts) > 3 else "",
            "题目": "-".join(parts[4:]) if len(parts) > 4 else "",
            "作者": "",
            "作者机构": "",
        }

    return {
        "编号": parts[0],
        "期刊": parts[1],
        "年份": parts[2],
        "期": parts[3],
        "题目": parts[4],
        "作者": parts[5],
        "作者机构": "-".join(parts[6:]),
    }


def extract_paper_text(pdf_path: Path, head_pages: int = 3, tail_pages: int = 2) -> str:
    """提取 PDF 关键章节文本"""
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)

    if total_pages <= head_pages + tail_pages + 2:
        pages = [page.get_text() for page in doc]
    else:
        head = [doc[i].get_text() for i in range(min(head_pages, total_pages))]
        tail_start = max(total_pages - tail_pages, head_pages)
        tail = [doc[i].get_text() for i in range(tail_start, total_pages)]
        pages = head + tail

    doc.close()
    text = "\n".join(pages)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


# ═══════════════════════════════════════════════════════════
# 阶段 3：关键词预筛 + 语义匹配
# ═══════════════════════════════════════════════════════════

def keyword_prefilter(text: str, keyword_index: dict) -> dict:
    """关键词预筛(差异化策略)"""
    disc_hits = {}
    disc_items = {}

    for kw, entries in keyword_index.items():
        if kw in text:
            for disc_key, category, item in entries:
                disc_hits[disc_key] = disc_hits.get(disc_key, 0) + 1
                if disc_key not in disc_items:
                    disc_items[disc_key] = {"标识性概念": set(), "原创性理论": set(), "框架结构": set()}
                disc_items[disc_key][category].add(item)

    sorted_discs = sorted(disc_hits.items(), key=lambda x: x[1], reverse=True)[:5]

    candidate_items = {}
    for disc_key in dict(sorted_discs):
        candidate_items[disc_key] = {
            cat: sorted(items) for cat, items in disc_items.get(disc_key, {}).items()
        }

    return {
        "top_disciplines": sorted_discs,
        "candidate_items": candidate_items,
    }


def merge_matches(keyword_result: dict, semantic_result: dict) -> dict:
    """合并关键词匹配和语义匹配结果"""
    merged = {}

    # 合并关键词结果
    for disc_key, cats in keyword_result["candidate_items"].items():
        if disc_key not in merged:
            merged[disc_key] = {"标识性概念": {}, "原创性理论": {}, "框架结构": {}}
        for cat, items in cats.items():
            for item in items:
                merged[disc_key][cat][item] = {"method": "keyword", "score": None}

    # 合并语义匹配结果
    for disc_key, cats in semantic_result.items():
        if disc_key not in merged:
            merged[disc_key] = {"标识性概念": {}, "原创性理论": {}, "框架结构": {}}
        for cat, item_scores in cats.items():
            for item, score in item_scores:
                if item in merged[disc_key][cat]:
                    # 已有关键词匹配，标记为双重匹配
                    merged[disc_key][cat][item] = {"method": "keyword+semantic", "score": score}
                else:
                    merged[disc_key][cat][item] = {"method": "semantic", "score": score}

    return merged


# ═══════════════════════════════════════════════════════════
# 阶段 4：LLM 语义验证（优化版 Prompt）
# ═══════════════════════════════════════════════════════════

def build_llm_prompt(
    paper_meta: dict,
    paper_text: str,
    merged_matches: dict,
) -> str:
    """构建 LLM 语义验证 prompt(优化版)"""

    # 构建候选条目文本
    candidate_text = ""
    for disc_key, cats in merged_matches.items():
        disc_name = disc_key.split("_", 1)[1] if "_" in disc_key else disc_key
        candidate_text += f"\n### {disc_name}\n"
        for cat, items_dict in cats.items():
            if items_dict:
                items_list = []
                for item, info in items_dict.items():
                    method = info["method"]
                    score = info["score"]
                    if score:
                        label = f"{item} [{method}, 相似度:{score:.2f}]"
                    else:
                        label = f"{item} [{method}]"
                    items_list.append(label)
                candidate_text += f"- **{cat}**：{'；'.join(items_list)}\n"

    # 截断论文文本
    max_text_len = 6000
    if len(paper_text) > max_text_len:
        paper_text = paper_text[:max_text_len] + "\n...(文本已截断)"

    prompt = (
        "你是一位法学学术评价专家。请分析以下法学论文与「中国法学自主知识体系」的关联程度。\n\n"
        "## 论文信息\n"
        f"- 题目：{paper_meta['题目']}\n"
        f"- 期刊：{paper_meta['期刊']}\n"
        f"- 作者：{paper_meta['作者']}\n\n"
        "## 论文关键文本\n"
        f"{paper_text}\n\n"
        "## 候选知识库条目（关键词 + 语义匹配结果）\n"
        f"{candidate_text}\n\n"
        "## 重要说明\n\n"
        "1. **标识性概念**：\n"
        "   - 忽略过于通用的词（如\"法律\"、\"法治\"等在所有论文中都会出现的词）\n"
        "   - 只匹配论文**核心讨论**的专业概念\n"
        "   - 需要明确的文本证据\n\n"
        "2. **原创性理论**：\n"
        "   - 论文可能使用简称（如\"法治体系\"指\"中国特色社会主义法治体系理论\"）\n"
        "   - 判断论文是否真正**讨论该理论的核心观点**\n"
        "   - 不要仅凭关键词出现就判定匹配\n\n"
        "3. **框架结构**：\n"
        "   - 论文很少直接说\"本体论\"、\"价值论\"等术语\n"
        "   - 需要分析论文的**论证结构**是否符合该框架\n"
        "   - 例如：论文讨论\"法的本质\"属于\"本体论\"框架\n\n"
        "## 任务\n\n"
        "请从上述候选条目中，判断该论文实际涉及了哪些条目，并提供证据。\n\n"
        "### 判断规则\n"
        "- 只选择有明确文本证据支撑的匹配项\n"
        "- 跨学科论文可以匹配多个学科的条目\n"
        "- 每个匹配项需要提供论文中的证据（引用原文片段）\n"
        "- 如果某个类别没有匹配项，返回空列表\n\n"
        "请以 JSON 格式输出，结构如下：\n"
        "```json\n"
        "{\n"
        '    "primary_discipline": "最主要的学科名称（如：刑法学）",\n'
        '    "secondary_disciplines": ["次要学科（如有）"],\n'
        '    "matches": [\n'
        "        {\n"
        '            "category": "标识性概念 或 原创性理论 或 框架结构",\n'
        '            "discipline": "所属学科名称",\n'
        '            "item": "匹配的知识库条目名称（使用知识库中的原始名称）",\n'
        '            "evidence": "论文中的证据片段（30字以内）",\n'
        '            "reasoning": "匹配理由（说明为何判定匹配）"\n'
        "        }\n"
        "    ],\n"
        '    "confidence": "high/medium/low，整体匹配置信度",\n'
        '    "note": "补充说明"\n'
        "}\n"
        "```"
    )

    return prompt


def call_llm(prompt: str) -> dict:
    """调用 Qwen3.6-Plus"""
    if not DASHSCOPE_API_KEY:
        print("⚠️  DASHSCOPE_API_KEY 未配置，跳过 LLM 验证")
        return None

    client = openai.OpenAI(
        api_key=DASHSCOPE_API_KEY,
        base_url=DASHSCOPE_BASE_URL,
    )

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        content = response.choices[0].message.content
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(content)
    except Exception as e:
        print(f"  ⚠️  LLM 调用失败：{e}")
        return None


# ═══════════════════════════════════════════════════════════
# 阶段 5：CSV 输出
# ═══════════════════════════════════════════════════════════

CSV_COLUMNS = [
    "编号", "期刊", "年份", "期", "题目", "作者", "作者机构",
    "主要学科", "标识性概念匹配", "原创性理论匹配", "框架结构匹配",
    "匹配条目总数", "匹配方法统计", "备注",
]


def format_llm_result(llm_result: dict, merged_matches: dict) -> dict:
    """将 LLM 结果格式化为 CSV 行数据"""
    if llm_result is None:
        # LLM 不可用，回退到合并匹配结果
        concepts = []
        theories = []
        frameworks = []
        disciplines = []
        method_stats = {"keyword": 0, "semantic": 0, "keyword+semantic": 0}

        for disc_key, cats in merged_matches.items():
            disc_name = disc_key.split("_", 1)[1] if "_" in disc_key else disc_key
            disciplines.append(disc_name)
            for cat, items_dict in cats.items():
                for item, info in items_dict.items():
                    method_stats[info["method"]] = method_stats.get(info["method"], 0) + 1
                    if cat == "标识性概念":
                        concepts.append(item)
                    elif cat == "原创性理论":
                        theories.append(item)
                    elif cat == "框架结构":
                        frameworks.append(item)

        method_str = f"keyword:{method_stats['keyword']}, semantic:{method_stats['semantic']}, both:{method_stats['keyword+semantic']}"

        return {
            "主要学科": "；".join(disciplines[:2]),
            "标识性概念匹配": "；".join(concepts[:10]),
            "原创性理论匹配": "；".join(theories[:10]),
            "框架结构匹配": "；".join(frameworks[:10]),
            "匹配条目总数": len(concepts) + len(theories) + len(frameworks),
            "匹配方法统计": method_str,
            "备注": "仅关键词+语义匹配（LLM 未调用）",
        }

    # 从 LLM 结果中提取
    matches = llm_result.get("matches", [])
    concepts = []
    theories = []
    frameworks = []

    for m in matches:
        cat = m.get("category", "")
        item = m.get("item", "")
        disc = m.get("discipline", "")
        label = f"{item}[{disc}]" if disc else item

        if "概念" in cat:
            concepts.append(label)
        elif "理论" in cat:
            theories.append(label)
        elif "框架" in cat:
            frameworks.append(label)

    primary = llm_result.get("primary_discipline", "")
    secondary = llm_result.get("secondary_disciplines", [])
    all_discs = [primary] + secondary if primary else secondary
    confidence = llm_result.get("confidence", "")
    note = llm_result.get("note", "")
    if confidence:
        note = f"置信度:{confidence}" + (f"；{note}" if note else "")

    # 统计匹配方法
    method_stats = {"keyword": 0, "semantic": 0, "keyword+semantic": 0, "llm_verified": len(matches)}
    for disc_key, cats in merged_matches.items():
        for cat, items_dict in cats.items():
            for item, info in items_dict.items():
                method_stats[info["method"]] = method_stats.get(info["method"], 0) + 1

    method_str = f"keyword:{method_stats['keyword']}, semantic:{method_stats['semantic']}, both:{method_stats['keyword+semantic']}, llm_verified:{method_stats['llm_verified']}"

    return {
        "主要学科": "；".join(all_discs),
        "标识性概念匹配": "；".join(concepts),
        "原创性理论匹配": "；".join(theories),
        "框架结构匹配": "；".join(frameworks),
        "匹配条目总数": len(concepts) + len(theories) + len(frameworks),
        "匹配方法统计": method_str,
        "备注": note,
    }


def write_csv(results: list, output_path: Path):
    """写入 CSV 文件"""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(results)

    print(f"\n✅ CSV 已写入：{output_path}")
    print(f"   共 {len(results)} 篇论文")


# ═══════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("Top 30 论文 × 树状知识库匹配分析（优化版 v2）")
    print("=" * 60)

    # 阶段 1：解析知识库
    print("\n📚 阶段 1：解析知识库...")
    knowledge = parse_knowledge_base(KNOWLEDGE_MD)
    total_concepts = sum(len(v["标识性概念"]) for v in knowledge.values())
    total_theories = sum(len(v["原创性理论"]) for v in knowledge.values())
    total_frameworks = sum(len(v["框架结构"]) for v in knowledge.values())
    print(f"   学科数：{len(knowledge)}")
    print(f"   标识性概念：{total_concepts}")
    print(f"   原创性理论：{total_theories}")
    print(f"   框架结构：{total_frameworks}")

    # 构建关键词索引
    print("\n📇 构建关键词索引（差异化策略）...")
    keyword_index = build_keyword_index(knowledge)
    print(f"   关键词索引条目：{len(keyword_index)}")

    # 构建语义索引
    print("\n🧠 构建语义索引（差异化策略）...")
    print(f"   加载 embedding 模型：{EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)

    cache_path = CACHE_DIR / "knowledge_embeddings_v2.npz"
    semantic_items, semantic_embeddings = build_semantic_index(knowledge, model, cache_path)
    print(f"   语义索引条目：{len(semantic_items)}")

    # 阶段 2-4：逐篇处理
    pdf_files = sorted(PAPER_DIR.glob("*.pdf"))
    print(f"\n📄 阶段 2-4：处理 {len(pdf_files)} 篇论文...")

    if not DASHSCOPE_API_KEY:
        print("⚠️  DASHSCOPE_API_KEY 未配置，将仅使用关键词+语义匹配")
    else:
        print(f"   LLM 模型：{MODEL_NAME}（DashScope）")

    results = []
    for i, pdf_path in enumerate(pdf_files):
        paper_meta = parse_paper_filename(pdf_path.name)
        print(f"\n  [{i+1}/{len(pdf_files)}] {paper_meta['题目'][:30]}...")

        # 阶段 2：PDF 文本提取
        try:
            paper_text = extract_paper_text(pdf_path)
            print(f"    文本提取：{len(paper_text)} 字")
        except Exception as e:
            print(f"    ❌ PDF 解析失败：{e}")
            results.append({
                **paper_meta,
                "主要学科": "",
                "标识性概念匹配": "",
                "原创性理论匹配": "",
                "框架结构匹配": "",
                "匹配条目总数": 0,
                "匹配方法统计": "",
                "备注": f"PDF解析失败：{e}",
            })
            continue

        # 阶段 3：关键词预筛
        keyword_result = keyword_prefilter(paper_text, keyword_index)
        print(f"    关键词匹配：{len(keyword_result['candidate_items'])} 个学科")

        # 阶段 3.5：语义匹配
        semantic_result = semantic_match(paper_text, semantic_items, semantic_embeddings, model)
        print(f"    语义匹配：{len(semantic_result)} 个学科")

        # 合并结果
        merged_matches = merge_matches(keyword_result, semantic_result)
        total_items = sum(len(items) for cats in merged_matches.values() for items in cats.values())
        print(f"    合并结果：{total_items} 个条目")

        # 阶段 4：LLM 语义验证
        llm_result = None
        if DASHSCOPE_API_KEY:
            prompt = build_llm_prompt(paper_meta, paper_text, merged_matches)
            llm_result = call_llm(prompt)
            if llm_result:
                primary = llm_result.get("primary_discipline", "未知")
                n_matches = len(llm_result.get("matches", []))
                print(f"    LLM 验证：主要学科={primary}，匹配 {n_matches} 项")
            else:
                print(f"    LLM 验证：失败，回退到关键词+语义匹配")
            time.sleep(0.5)

        # 格式化结果
        formatted = format_llm_result(llm_result, merged_matches)
        results.append({**paper_meta, **formatted})

    # 阶段 5：CSV 输出
    print(f"\n📊 阶段 5：写入 CSV...")
    write_csv(results, OUTPUT_CSV)

    # 汇总统计
    print("\n" + "=" * 60)
    print("汇总统计")
    print("=" * 60)
    total_matches = sum(r["匹配条目总数"] for r in results)
    avg_matches = total_matches / len(results) if results else 0
    print(f"   论文总数：{len(results)}")
    print(f"   匹配条目总计：{total_matches}")
    print(f"   平均匹配条目/篇：{avg_matches:.1f}")

    # 学科分布
    disc_count = {}
    for r in results:
        for d in r["主要学科"].split("；"):
            d = d.strip()
            if d:
                disc_count[d] = disc_count.get(d, 0) + 1
    print(f"\n   学科分布（Top 5）：")
    for d, c in sorted(disc_count.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"     {d}：{c} 篇")


if __name__ == "__main__":
    main()

