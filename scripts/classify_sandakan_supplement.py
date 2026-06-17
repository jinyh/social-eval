#!/usr/bin/env python3
"""
补测 604 篇漏检论文的学科分类，并融合专家修正。

流程:
  1. 识别 sandakan-ai-classification.json 中缺失的论文
  2. 使用 qwen3.7-max (DashScope) 对缺失论文做学科分类
  3. 将结果写回 sandakan-ai-classification.json
  4. 融合专家修正（学科归类错误条目.md + 学科错误条目6-15.md）
  5. 更新 sandakan-new-metadata.csv（添加主/次分类列）

用法:
  uv run python scripts/classify_sandakan_supplement.py          # 补测+融合
  uv run python scripts/classify_sandakan_supplement.py --dry-run # 只检查，不调 API
"""

import argparse
import asyncio
import csv
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import openai
from dotenv import load_dotenv

load_dotenv()

# ── 配置 ──
MODEL = "qwen3.7-max"
TEMPERATURE = 0.3
CONCURRENCY = 8
TIMEOUT = 60
MAX_RETRIES = 2

CSV_PATH = Path("results/sandakan-new-metadata.csv")
LLM_PATH = Path("results/sandakan-ai-classification.json")
EXPERT1_PATH = Path("results/e2-top102/学科归类错误条目.md")
EXPERT2_PATH = Path("results/e2-top102/学科错误条目6-15.md")

VALID_CATEGORIES = [
    "民商法学", "刑法学", "宪法学与行政法学", "诉讼法学", "法学理论",
    "环境与资源保护法学", "国际法学", "经济法学", "知识产权法学",
    "法律史", "党内法规学",
]

CATEGORY_LIST = "、".join(VALID_CATEGORIES)
CATEGORY_MAPPING = {
    "劳动法与社会保障法学": "民商法学",
    "劳动法学": "民商法学",
    "社会保障法学": "民商法学",
}

PROMPT_TEMPLATE = """\
你是一位法学学科分类专家。根据论文标题和作者机构，判断该论文所属的法学二级学科。

可选学科（11个）：{categories}

## 分类规则

1. **劳动法、社会保障法方向**归入"民商法学"（非经济法学）。
2. **标题含民法核心概念**（赔偿、债务、信托、权利体系、诚实信用、公序良俗、监护、占有、夫妻、财产私法保护、自甘冒险）→ 归入"民商法学"，即使标题含"理论""解释论"等理论用语。
3. **标题含刑法教义学概念**（具体罪名如抢劫罪/行贿罪/敲诈勒索罪、被害人、自陷风险、注意义务）→ 归入"刑法学"，即使标题含"法理内涵""规范本质"等理论用语。
4. **标题含宪法概念**（合宪性、基本权利）→ 归入"宪法学与行政法学"。
5. **标题含涉外/准据法** → 归入"国际法学"，即使涉及私法问题。
6. **标题偏法哲学/认识论**（证据客观性、理由模式、功能限度）→ 归入"法学理论"，即使涉及诉讼制度。
7. **区分原则**：看论文的**核心贡献**属于哪个学科，而非标题中出现的背景领域。例如"生态环境损害赔偿的理论构成"的核心贡献是损害赔偿的私法构造（民商法学），而非环境保护（环境法学）。
8. **学科惯性原则**：论文的原始学科归属通常来自作者的学科定位和研究方向，除非标题有压倒性证据指向另一学科，否则不应轻易改变。标题中出现跨学科术语（如"行政违法性""数据爬取""跨法域"）往往只是研究背景，不代表核心贡献转移。

## 示例

标题：抢劫罪与敲诈勒索罪之界分：基于被害人的处分自由
机构：北京大学法学院
→ {{"主分类": "刑法学", "主分类概率": 0.95, "次分类": "法学理论", "次分类概率": 0.05}}

标题：公序良俗原则与诚实信用原则的区分
机构：中国政法大学民商经济法学院
→ {{"主分类": "民商法学", "主分类概率": 0.95, "次分类": "法学理论", "次分类概率": 0.05}}

标题：劳动关系认定的理论澄清与规范建构
机构：上海交通大学凯原法学院
→ {{"主分类": "民商法学", "主分类概率": 0.95, "次分类": "经济法学", "次分类概率": 0.05}}

标题：基于决定关系的证据客观性：概念、功能与理论定位
机构：中国人民大学法学院
→ {{"主分类": "法学理论", "主分类概率": 0.90, "次分类": "诉讼法学", "次分类概率": 0.10}}

标题：调整个性化定价的公私法协动体系构造
机构：南京大学法学院
→ {{"主分类": "民商法学", "主分类概率": 0.85, "次分类": "经济法学", "次分类概率": 0.13}}

标题：行政违法性认识错误的性质与处理规则
机构：南京大学法学院
→ {{"主分类": "刑法学", "主分类概率": 0.95, "次分类": "宪法学与行政法学", "次分类概率": 0.05}}
（"行政违法性"是刑法中行政犯的前提概念，核心贡献是刑法教义学，不归宪法学与行政法学）

标题：数据爬取的正当性及其边界
机构：对外经济贸易大学法学院
→ {{"主分类": "民商法学", "主分类概率": 0.90, "次分类": "经济法学", "次分类概率": 0.10}}
（数据爬取涉及数据权益保护和不正当竞争，核心是民商法问题，不归经济法学）

标题：跨法域合同纠纷中强制性规范的类型及认定规则
机构：浙江师范大学法政学院
→ {{"主分类": "民商法学", "主分类概率": 0.85, "次分类": "国际法学", "次分类概率": 0.15}}
（"跨法域"是背景语境，核心贡献是合同效力中强制性规范的私法理论，不归国际法学）

标题："正当信赖"的衡平检验
机构：北京大学法学院
→ {{"主分类": "法学理论", "主分类概率": 0.85, "次分类": "宪法学与行政法学", "次分类概率": 0.15}}
（信赖保护原则横跨公法与私法，论文侧重法理层面的衡平理论建构，不归民商法学）

## 待分类论文

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


# ── 数据读写 ──


def load_papers() -> list[dict]:
    """读取元数据 CSV。"""
    with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_llm_results() -> dict[int, dict]:
    """加载已有的 LLM 分类结果。"""
    if not LLM_PATH.exists():
        return {}
    with open(LLM_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {int(k): v for k, v in data.items()}


def save_llm_results(results: dict[int, dict]):
    """保存 LLM 分类结果。"""
    serializable = {str(k): v for k, v in results.items()}
    with open(LLM_PATH, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)


# ── 专家修正解析 ──


def parse_expert1(path: Path) -> list[dict]:
    """解析学科归类错误条目.md（按标题匹配）。"""
    corrections = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|") or line.startswith("| #") or line.startswith("|---"):
                continue
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 9 and parts[0].isdigit():
                target = parts[8].replace("应当归类于", "").strip()
                target = CATEGORY_MAPPING.get(target, target)
                corrections.append({
                    "expert_orig": parts[2],
                    "title": parts[5],
                    "author": parts[6],
                    "target": target,
                })
    return corrections


def parse_expert2(path: Path) -> list[dict]:
    """解析学科错误条目6-15.md（按 PID 匹配）。"""
    corrections = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|") or line.startswith("| 排名") or line.startswith("| ---"):
                continue
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 10 and parts[0].strip().isdigit():
                pid = int(parts[1])
                target = parts[9]
                target = CATEGORY_MAPPING.get(target, target)
                corrections.append({
                    "pid": pid,
                    "expert_orig": parts[7],
                    "target": target,
                    "title": parts[2],
                })
    return corrections


def normalize_title(title: str) -> str:
    """标准化标题用于匹配：移除引号/空格，统一冒号，取主标题。"""
    t = title.strip()
    t = t.replace("\uff1a", ":").replace("\uff08", "(").replace("\uff09", ")")
    t = t.replace("\u201c", "").replace("\u201d", "").replace('"', '')
    t = t.replace("'", "").replace("\u2018", "").replace("\u2019", "")
    t = re.sub(r'\s+', '', t)
    if ":" in t:
        t = t.split(":")[0]
    return t.strip()



def build_expert_map(papers: list[dict], exp1: list[dict], exp2: list[dict]) -> dict:
    """构建 PID → 专家修正的映射。"""
    # 用标准化标题建索引
    title_to_pid = {normalize_title(r["题目"]): int(r["编号"]) for r in papers}
    expert_map = {}

    # 文件 1：按标准化标题匹配
    matched = 0
    for corr in exp1:
        norm = normalize_title(corr["title"])
        pid = title_to_pid.get(norm)
        if pid is not None:
            expert_map[pid] = {
                "target": corr["target"],
                "expert_orig": corr["expert_orig"],
                "source": "expert1",
            }
            matched += 1
        else:
            print(f"  ⚠️ 专家文件1未匹配: {corr['title'][:30]}...")
    print(f"  专家文件1: {matched}/{len(exp1)} 条匹配成功")

    # 文件 2：按 PID 直接匹配
    for corr in exp2:
        expert_map[corr["pid"]] = {
            "target": corr["target"],
            "expert_orig": corr["expert_orig"],
            "source": "expert2",
        }
    print(f"  专家文件2: {len(exp2)} 条直接匹配")

    return expert_map


# ── LLM 调用 ──


def extract_json(text: str) -> dict:
    """从 LLM 输出中提取 JSON。"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
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
    for key in ("主分类", "主分类概率", "次分类", "次分类概率"):
        if key not in result:
            raise ValueError(f"缺少字段: {key}")

    result["主分类"] = CATEGORY_MAPPING.get(result["主分类"], result["主分类"])
    result["次分类"] = CATEGORY_MAPPING.get(result["次分类"], result["次分类"])

    if result["主分类"] not in VALID_CATEGORIES:
        raise ValueError(f"无效主分类: {result['主分类']}")
    if result["次分类"] not in VALID_CATEGORIES:
        raise ValueError(f"无效次分类: {result['次分类']}")

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
                return result

            except Exception as e:
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(2 ** attempt)
                    continue
                print(f"  ❌ PID {pid} 失败 ({title[:20]}...): {e}", flush=True)
                return None


# ── 融合逻辑 ──


def fuse(llm_result: dict, expert: dict | None, csv_class: str) -> dict:
    """
    融合 LLM 分类与专家修正。

    情形:
      A -- LLM 与专家一致（概率加 0.10）
      B -- LLM 与专家不一致（以专家为准，LLM 降为次分类）
      D -- 无专家审阅（直接用 LLM）
    """
    llm_main = llm_result["主分类"]
    llm_main_p = float(llm_result["主分类概率"])
    llm_sec = llm_result["次分类"]
    llm_sec_p = float(llm_result["次分类概率"])

    if expert is None:
        return {
            "主分类": llm_main,
            "主分类概率": llm_main_p,
            "次分类": llm_sec,
            "次分类概率": llm_sec_p,
            "情形": "D",
        }

    target = expert["target"]

    if llm_main == target:
        # 情形 A: LLM 与专家一致（boost 但保证 p1+p2 <= 0.98）
        boosted_p = min(llm_main_p + 0.05, 0.95)
        if boosted_p + llm_sec_p > 0.98:
            boosted_p = round(0.98 - llm_sec_p, 3)
        boosted_p = max(boosted_p, llm_main_p)  # 不低于原值
        return {
            "主分类": llm_main,
            "主分类概率": round(boosted_p, 3),
            "次分类": llm_sec,
            "次分类概率": llm_sec_p,
            "情形": "A",
        }

    # 情形 B: LLM 与专家不一致 -- 以专家为准
    main_p = max(llm_main_p, 0.75)
    adjusted_sec_p = min(llm_main_p * 0.3, 0.20)
    # 概率约束: main_p + adjusted_sec_p <= 0.98
    if main_p + adjusted_sec_p > 0.98:
        adjusted_sec_p = round(0.98 - main_p, 3)
    adjusted_sec_p = max(0.0, adjusted_sec_p)

    return {
        "主分类": target,
        "主分类概率": round(main_p, 3),
        "次分类": llm_main,
        "次分类概率": round(adjusted_sec_p, 3),
        "情形": "B",
    }




# ── 主流程 ──


async def run_supplement(papers: list[dict], todo: list[dict], results: dict[int, dict]):
    """补测缺失论文。"""
    client = openai.AsyncOpenAI(
        api_key=os.getenv("DASHSCOPE_API_KEY", ""),
        base_url=os.getenv(
            "DASHSCOPE_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
    )

    semaphore = asyncio.Semaphore(CONCURRENCY)
    completed = 0
    failed = 0
    save_counter = 0

    async def process_one(paper):
        nonlocal completed, failed, save_counter
        pid = int(paper["编号"])
        r = await classify_one(
            client, pid, paper["题目"], paper["作者机构"], semaphore,
        )
        if r is not None:
            results[pid] = r
            completed += 1
        else:
            failed += 1
        save_counter += 1
        if save_counter % 20 == 0:
            save_llm_results(results)
            print(
                f"  进度: {completed + failed}/{len(todo)} "
                f"(成功 {completed}, 失败 {failed})",
                flush=True,
            )

    tasks = [asyncio.create_task(process_one(p)) for p in todo]
    await asyncio.gather(*tasks)

    save_llm_results(results)
    return completed, failed


def run_merge(papers: list[dict], results: dict[int, dict], expert_map: dict):
    """融合 LLM + 专家修正，更新 CSV。"""
    fields = list(papers[0].keys())
    for col in ["主分类", "主分类概率", "次分类", "次分类概率", "分类情形"]:
        if col not in fields:
            fields.append(col)

    scenario_count = {"A": 0, "B": 0, "C": 0, "D": 0}
    fallback_count = 0
    output_rows = []

    for paper in papers:
        pid = int(paper["编号"])
        csv_class = paper.get("分类", "")

        if pid in results:
            llm_result = results[pid]
        else:
            llm_result = {
                "主分类": csv_class,
                "主分类概率": 0.60,
                "次分类": "",
                "次分类概率": 0.0,
            }
            fallback_count += 1

        expert = expert_map.get(pid)
        fused = fuse(llm_result, expert, csv_class)
        scenario_count[fused["情形"]] += 1

        paper["主分类"] = fused["主分类"]
        paper["主分类概率"] = fused["主分类概率"]
        paper["次分类"] = fused["次分类"]
        paper["次分类概率"] = fused["次分类概率"]
        paper["分类情形"] = fused["情形"]
        output_rows.append(paper)

    # 写入 CSV
    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output_rows)

    return output_rows, scenario_count, fallback_count


def print_report(output_rows: list[dict], scenario_count: dict, fallback_count: int,
                  expert_map: dict, supplemented: int):
    """输出最终报告。"""
    print(f"\n{'=' * 60}")
    print("最终报告")
    print(f"{'=' * 60}")

    # 分布统计
    main_dist = Counter(r["主分类"] for r in output_rows)
    print(f"\n主分类分布 ({len(output_rows)} 篇):")
    for cls, cnt in main_dist.most_common():
        print(f"  {cls:20s} {cnt:4d} ({cnt / len(output_rows) * 100:.1f}%)")

    # 情形统计
    print(f"\n融合情形分布:")
    print(f"  A (LLM=专家一致): {scenario_count['A']}")
    print(f"  B (LLM≠专家修正): {scenario_count['B']}")
    print(f"  C (历史已修正):    {scenario_count['C']}")
    print(f"  D (无专家审阅):    {scenario_count['D']}")

    if fallback_count:
        print(f"\n⚠️ LLM fallback (未分类，回退到 CSV 原值): {fallback_count} 篇")

    # 概率约束检查
    violations = []
    for r in output_rows:
        p1 = float(r["主分类概率"])
        p2 = float(r["次分类概率"])
        if p1 + p2 > 1.001:
            violations.append((int(r["编号"]), p1, p2))
    if violations:
        print(f"\n⚠️ 概率约束违规: {len(violations)} 条")
        for pid, p1, p2 in violations[:5]:
            print(f"  PID {pid}: {p1} + {p2} = {p1 + p2:.3f}")
    else:
        print(f"\n✅ 概率约束: 全部通过")

    # 专家条目逐条验证
    print(f"\n专家修正条目验证:")
    for r in output_rows:
        pid = int(r["编号"])
        if pid in expert_map:
            exp = expert_map[pid]
            match_mark = "✅" if r["主分类"] == exp["target"] else "⚠️"
            print(
                f"  PID {pid:4d} [{r['分类情形']}] {match_mark} "
                f"主={r['主分类']}({r['主分类概率']}) "
                f"次={r['次分类'] or '(空)'}({r['次分类概率']}) "
                f"| 原={r.get('分类', '?')} → 专家={exp['target']}"
            )


async def main():
    parser = argparse.ArgumentParser(description="补测 sandakan 分类 + 融合专家修正")
    parser.add_argument("--dry-run", action="store_true", help="只检查漏检情况，不调 API")
    args = parser.parse_args()

    print(f"{'=' * 60}")
    print("sandakan 分类补测 + 专家修正融合")
    print(f"{'=' * 60}")

    # ── Step 1: 识别漏检 ──
    print(f"\n1. 识别漏检论文...")
    papers = load_papers()
    results = load_llm_results()
    print(f"  元数据: {len(papers)} 篇")
    print(f"  已分类: {len(results)} 篇")

    todo = [p for p in papers if int(p["编号"]) not in results]
    print(f"  漏检: {len(todo)} 篇")

    if not todo:
        print("  ✅ 全部已分类，无需补测")
    else:
        # 按期刊统计漏检
        journal_dist = Counter(p["期刊"] for p in todo)
        print(f"  漏检期刊分布:")
        for j, c in journal_dist.most_common():
            print(f"    {j}: {c} 篇")

    # ── Step 2: 加载专家修正 ──
    print(f"\n2. 加载专家修正...")
    exp1 = parse_expert1(EXPERT1_PATH) if EXPERT1_PATH.exists() else []
    exp2 = parse_expert2(EXPERT2_PATH) if EXPERT2_PATH.exists() else []
    print(f"  专家文件1: {len(exp1)} 条")
    print(f"  专家文件2: {len(exp2)} 条")
    expert_map = build_expert_map(papers, exp1, exp2)
    print(f"  有效修正: {len(expert_map)} 条")

    # 检查专家修正是否涉及漏检论文
    expert_in_todo = [pid for pid in expert_map if pid not in results]
    if expert_in_todo:
        print(f"  ⚠️ 专家修正中有 {len(expert_in_todo)} 篇在漏检列表中 "
              f"(PID: {expert_in_todo})")

    if args.dry_run:
        print(f"\n[dry-run] 不执行补测，退出。")
        return

    # ── Step 3: 补测 ──
    if todo:
        print(f"\n3. 补测 {len(todo)} 篇 (模型: {MODEL}, 并发: {CONCURRENCY})...")
        completed, failed = await run_supplement(papers, todo, results)
        print(f"  完成: {completed}, 失败: {failed}")
        print(f"  总计: {len(results)}/{len(papers)}")
    else:
        print(f"\n3. 跳过补测（无漏检）")

    # ── Step 4: 融合 ──
    print(f"\n4. 融合 LLM + 专家修正...")
    # 重新加载（补测后更新）
    results = load_llm_results()
    output_rows, scenario_count, fallback_count = run_merge(papers, results, expert_map)
    print(f"  写入: {CSV_PATH}")
    print(f"  列数: {len(output_rows[0].keys())}, 行数: {len(output_rows)}")

    # ── Step 5: 报告 ──
    supplemented = len(todo) if todo else 0
    print_report(output_rows, scenario_count, fallback_count, expert_map, supplemented)

    print(f"\n✅ 完成！结果已保存到 {CSV_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
