#!/usr/bin/env python3
"""
Top 30 论文 × 树状知识库匹配分析

逐篇检测 raw/top30_paper/ 中的论文是否与 knowledge/中国法学自主知识体系-树状知识库.md
中的标识性概念、原创性理论、框架结构相关联，输出 CSV 文件。

方法：关键词预筛 + LLM 语义验证（Qwen3.6-Plus via DashScope）
"""

import csv
import json
import os
import re
import sys
import time
from pathlib import Path

import fitz  # PyMuPDF
import openai

# ── 路径配置 ──────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_MD = PROJECT_ROOT / "knowledge" / "中国法学自主知识体系-树状知识库.md"
PAPER_DIR = PROJECT_ROOT / "raw" / "top30_paper"
OUTPUT_CSV = PROJECT_ROOT / "results" / "top30-knowledge-matching.csv"

# ── LLM 配置（DashScope 兼容 OpenAI API） ────────────────

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL_NAME = "qwen3.6-plus"
TEMPERATURE = 0.3
MAX_TOKENS = 4096

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
# 阶段 1：解析知识库
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
    # 匹配学科行：如 "├── 1. 法理学自主知识体系 〔d01〕〔主干学科〕"
    # 或 "└── 22. 人权法学自主知识体系 〔d22〕〔新兴学科〕"
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
        # 确定当前学科的行范围
        start_line = disc["line"]
        if idx + 1 < len(disciplines):
            end_line = disciplines[idx + 1]["line"]
        else:
            end_line = len(lines)

        section_lines = lines[max(0, start_line):end_line]
        section_text = "\n".join(section_lines)

        entry = {
            "标识性概念": [],
            "原创性理论": [],
            "框架结构": [],
        }

        # 提取条目：匹配 "│   │   ├── 1. xxx" 格式
        # 条目在 "二、标识性概念"、"三、原创性理论"、"四、框架结构" 下面
        current_section = None
        for sline in section_lines:
            # 检测章节标题
            if re.search(r"二、标识性概念", sline):
                current_section = "标识性概念"
                continue
            elif re.search(r"三、原创性理论", sline):
                current_section = "原创性理论"
                continue
            elif re.search(r"四、框架结构", sline):
                current_section = "框架结构"
                continue
            # 新的大章节开始时重置
            elif re.search(r"[一二三四五六七八九十]、(?!标识性概念|原创性理论|框架结构)", sline):
                if current_section and not re.search(r"(标识性概念|原创性理论|框架结构)", sline):
                    # 只有遇到完全不同的大章节才重置
                    pass

            if current_section is None:
                continue

            # 匹配带编号的条目："1. xxx" 或 "(一) xxx"
            item_match = re.search(r"├──\s*(?:\d+\.\s*|\(\S+?\)\s*)?(.+)", sline)
            if not item_match:
                item_match = re.search(r"└──\s*(?:\d+\.\s*|\(\S+?\)\s*)?(.+)", sline)

            if item_match:
                item_text = item_match.group(1).strip()
                # 跳过子层级条目（含更多缩进的子项）
                if item_text and not item_text.startswith("├") and not item_text.startswith("└"):
                    entry[current_section].append(item_text)

        knowledge[disc["key"]] = entry

    return knowledge


def build_keyword_index(knowledge: dict) -> dict:
    """
    为每个知识库条目生成匹配关键词。
    返回 {keyword: [(discipline, category, item), ...]}
    """
    index = {}

    for disc_key, sections in knowledge.items():
        for category, items in sections.items():
            for item in items:
                # 生成关键词变体
                keywords = _generate_keywords(item)
                for kw in keywords:
                    if kw not in index:
                        index[kw] = []
                    index[kw].append((disc_key, category, item))

    return index


def _generate_keywords(item: str) -> list:
    """为一个条目生成搜索关键词列表"""
    keywords = set()

    # 原始名称
    clean = re.sub(r"[（(].+?[）)]", "", item).strip()
    if len(clean) >= 2:
        keywords.add(clean)

    # 去掉引号
    quote_chars = "“”「」『』"  # ""「」『』
    unquoted = clean.strip(quote_chars)
    if len(unquoted) >= 2:
        keywords.add(unquoted)

    # 对含"理论""论""原则""制度"的条目，也加短关键词
    for suffix in ["理论", "论", "原则", "制度", "体系", "机制", "观"]:
        if clean.endswith(suffix) and len(clean) > len(suffix) + 2:
            base = clean[: -len(suffix)]
            if len(base) >= 2:
                keywords.add(base)

    # 过滤太短的关键词（< 2 字符容易误匹配）
    return [kw for kw in keywords if len(kw) >= 2]


# ═══════════════════════════════════════════════════════════
# 阶段 2：PDF 文本提取
# ═══════════════════════════════════════════════════════════

def parse_paper_filename(filename: str) -> dict:
    """
    从文件名解析论文元数据。
    格式：编号-期刊-年份-期-题目-作者-机构.pdf
    """
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
    """
    提取 PDF 关键章节文本。
    - 前 head_pages 页（标题、摘要、引言）
    - 后 tail_pages 页（结语/结论）
    - 如果全文 <= 10 页则取全文
    """
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)

    if total_pages <= head_pages + tail_pages + 2:
        # 短篇论文取全文
        pages = [page.get_text() for page in doc]
    else:
        # 取前 N 页 + 后 M 页
        head = [doc[i].get_text() for i in range(min(head_pages, total_pages))]
        tail_start = max(total_pages - tail_pages, head_pages)
        tail = [doc[i].get_text() for i in range(tail_start, total_pages)]
        pages = head + tail

    doc.close()
    text = "\n".join(pages)

    # 清理多余空白
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


# ═══════════════════════════════════════════════════════════
# 阶段 3：关键词预筛
# ═══════════════════════════════════════════════════════════

def keyword_prefilter(text: str, keyword_index: dict) -> dict:
    """
    关键词预筛：扫描文本中的关键词命中。

    返回：
    {
        "top_disciplines": [("d11_刑法学", 15), ...],  # Top-5 学科及命中数
        "candidate_items": {
            "d11_刑法学": {
                "标识性概念": ["正当防卫", ...],
                "原创性理论": ["社会危害性理论", ...],
                "框架结构": []
            },
            ...
        }
    }
    """
    # 统计每个学科的命中数
    disc_hits = {}  # {disc_key: count}
    disc_items = {}  # {disc_key: {category: set(items)}}

    for kw, entries in keyword_index.items():
        if kw in text:
            for disc_key, category, item in entries:
                disc_hits[disc_key] = disc_hits.get(disc_key, 0) + 1
                if disc_key not in disc_items:
                    disc_items[disc_key] = {"标识性概念": set(), "原创性理论": set(), "框架结构": set()}
                disc_items[disc_key][category].add(item)

    # 按命中数排序取 Top-5
    sorted_discs = sorted(disc_hits.items(), key=lambda x: x[1], reverse=True)[:5]

    # 转换为列表格式
    candidate_items = {}
    for disc_key in dict(sorted_discs):
        candidate_items[disc_key] = {
            cat: sorted(items) for cat, items in disc_items.get(disc_key, {}).items()
        }

    return {
        "top_disciplines": sorted_discs,
        "candidate_items": candidate_items,
    }


# ═══════════════════════════════════════════════════════════
# 阶段 4：LLM 语义验证
# ═══════════════════════════════════════════════════════════

def build_llm_prompt(
    paper_meta: dict,
    paper_text: str,
    prefilter_result: dict,
    knowledge: dict,
) -> str:
    """构建 LLM 语义验证 prompt"""

    # 构建候选知识库条目文本
    candidate_text = ""
    for disc_key, cats in prefilter_result["candidate_items"].items():
        disc_name = disc_key.split("_", 1)[1] if "_" in disc_key else disc_key
        candidate_text += f"\n### {disc_name}\n"
        for cat, items in cats.items():
            if items:
                candidate_text += f"- **{cat}**：{'；'.join(items)}\n"

    # 如果候选太少，补充所有学科的标识性概念列表
    if not candidate_text.strip():
        candidate_text = "\n（关键词预筛未命中，以下是各学科的核心条目供参考）\n"
        for disc_key, sections in knowledge.items():
            disc_name = disc_key.split("_", 1)[1] if "_" in disc_key else disc_key
            concepts = "；".join(sections["标识性概念"][:10])
            theories = "；".join(sections["原创性理论"][:5])
            candidate_text += f"\n### {disc_name}\n"
            if concepts:
                candidate_text += f"- **标识性概念**：{concepts}\n"
            if theories:
                candidate_text += f"- **原创性理论**：{theories}\n"

    # 截断论文文本防止超长
    max_text_len = 6000
    if len(paper_text) > max_text_len:
        paper_text = paper_text[:max_text_len] + "\n...(文本已截断)"

    prompt = f"""你是一位法学学术评价专家。请分析以下法学论文与「中国法学自主知识体系」的关联程度。

## 论文信息
- 题目：{paper_meta['题目']}
- 期刊：{paper_meta['期刊']}
- 作者：{paper_meta['作者']}

## 论文关键文本
{paper_text}

## 候选知识库条目（关键词预筛结果）
{candidate_text}

## 任务

请从上述候选条目中，判断该论文实际涉及了哪些：
1. **标识性概念**：论文核心讨论的法学概念（需在知识库中有对应条目，或虽名称不同但实质相同）
2. **原创性理论**：论文运用或讨论的法学理论
3. **框架结构**：论文的论证框架与知识库中哪个学科的理论框架相关

### 判断规则
- 只选择有明确文本证据支撑的匹配项，不要仅凭学科领域推测
- 跨学科论文可以匹配多个学科的条目
- 每个匹配项需要提供论文中的证据（引用原文片段）
- 如果某个类别没有匹配项，返回空列表

请以 JSON 格式输出，结构如下：
```json
{{
    "primary_discipline": "最主要的学科名称（如：刑法学）",
    "secondary_disciplines": ["次要学科（如有）"],
    "matches": [
        {{
            "category": "标识性概念 或 原创性理论 或 框架结构",
            "discipline": "所属学科名称",
            "item": "匹配的知识库条目名称（使用知识库中的原始名称）",
            "evidence": "论文中的证据片段（30字以内）"
        }}
    ],
    "confidence": "high/medium/low，整体匹配置信度",
    "note": "补充说明（如跨学科特点、匹配置信度理由等）"
}}
```"""

    return prompt


def call_llm(prompt: str) -> dict:
    """调用 Qwen3.6-Plus（通过 DashScope 兼容 API）"""
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
        # 提取 JSON
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
    "匹配条目总数", "备注",
]


def format_llm_result(llm_result: dict, prefilter: dict) -> dict:
    """将 LLM 结果格式化为 CSV 行数据"""
    if llm_result is None:
        # LLM 不可用，回退到关键词预筛结果
        concepts = []
        theories = []
        frameworks = []
        disciplines = []
        for disc_key, cats in prefilter["candidate_items"].items():
            disc_name = disc_key.split("_", 1)[1] if "_" in disc_key else disc_key
            disciplines.append(disc_name)
            concepts.extend(cats.get("标识性概念", []))
            theories.extend(cats.get("原创性理论", []))
            frameworks.extend(cats.get("框架结构", []))

        return {
            "主要学科": "；".join(disciplines[:2]),
            "标识性概念匹配": "；".join(concepts),
            "原创性理论匹配": "；".join(theories),
            "框架结构匹配": "；".join(frameworks),
            "匹配条目总数": len(concepts) + len(theories) + len(frameworks),
            "备注": "仅关键词预筛（LLM 未调用）",
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

    return {
        "主要学科": "；".join(all_discs),
        "标识性概念匹配": "；".join(concepts),
        "原创性理论匹配": "；".join(theories),
        "框架结构匹配": "；".join(frameworks),
        "匹配条目总数": len(concepts) + len(theories) + len(frameworks),
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
    print("Top 30 论文 × 树状知识库匹配分析")
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

    keyword_index = build_keyword_index(knowledge)
    print(f"   关键词索引条目：{len(keyword_index)}")

    # 阶段 2 & 3 & 4：逐篇处理
    pdf_files = sorted(PAPER_DIR.glob("*.pdf"))
    print(f"\n📄 阶段 2-4：处理 {len(pdf_files)} 篇论文...")

    if not DASHSCOPE_API_KEY:
        print("⚠️  DASHSCOPE_API_KEY 未配置，将仅使用关键词预筛")
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
                "备注": f"PDF解析失败：{e}",
            })
            continue

        # 阶段 3：关键词预筛
        prefilter = keyword_prefilter(paper_text, keyword_index)
        top_discs = prefilter["top_disciplines"]
        print(f"    关键词预筛：命中 {len(top_discs)} 个学科")
        for disc_key, count in top_discs[:3]:
            disc_name = disc_key.split("_", 1)[1]
            print(f"      - {disc_name}（{count} 命中）")

        # 阶段 4：LLM 语义验证
        llm_result = None
        if DASHSCOPE_API_KEY:
            prompt = build_llm_prompt(paper_meta, paper_text, prefilter, knowledge)
            llm_result = call_llm(prompt)
            if llm_result:
                primary = llm_result.get("primary_discipline", "未知")
                n_matches = len(llm_result.get("matches", []))
                print(f"    LLM 验证：主要学科={primary}，匹配 {n_matches} 项")
            else:
                print(f"    LLM 验证：失败，回退到关键词预筛")
            # 简单限流
            time.sleep(0.5)

        # 格式化结果
        formatted = format_llm_result(llm_result, prefilter)
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
