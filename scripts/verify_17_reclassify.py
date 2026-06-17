#!/usr/bin/env python3
"""
验证改进后的分类 prompt（纯标准库版本，无需 openai SDK）
对 17 条"AI 完全改变分类"的论文重跑，对比新旧结果。
"""

import csv
import http.client
import json
import os
import re
import ssl
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

CSV_PATH = Path("results/sandakan-new-metadata.csv")
CANDIDATE_PATH = Path("results/candidate-reclassified-71.csv")

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


def load_env():
    """Read .env file manually."""
    env = {}
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def call_api(title: str, institution: str, api_key: str, base_url: str) -> dict | None:
    """Call DashScope API using http.client (no SDK needed)."""
    prompt = PROMPT_TEMPLATE.format(
        categories=CATEGORY_LIST,
        title=title,
        institution=institution,
    )

    payload = json.dumps({
        "model": "qwen3.7-max",
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
    })

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    # Parse base_url to get host and path prefix
    # e.g. "https://dashscope.aliyuncs.com/compatible-mode/v1"
    url_path = base_url.replace("https://", "").replace("http://", "")
    host = url_path.split("/")[0]
    path_prefix = "/" + "/".join(url_path.split("/")[1:]) if "/" in url_path else ""
    api_path = f"{path_prefix}/chat/completions"

    ctx = ssl.create_default_context()

    for attempt in range(3):
        try:
            conn = http.client.HTTPSConnection(host, 443, timeout=60, context=ctx)
            conn.request("POST", api_path, body=payload, headers=headers)
            resp = conn.getresponse()
            data = json.loads(resp.read().decode("utf-8"))
            conn.close()
            content = data["choices"][0]["message"]["content"]
            return extract_json(content)
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
                continue
            print(f"  ❌ API error for '{title[:20]}': {e}", flush=True)
            return None


def extract_json(text: str) -> dict:
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


def load_17_papers() -> list[dict]:
    """从 candidate-reclassified-71.csv 中筛选 17 条 AI次分类!=原分类 的论文。"""
    with open(CANDIDATE_PATH, "r", encoding="utf-8-sig") as f:
        candidates = list(csv.DictReader(f))

    corrected_ids = {"696", "442", "1878", "1621", "1787", "1229", "1405", "1679"}

    target_pids = set()
    for r in candidates:
        if r["编号"] in corrected_ids:
            continue
        if r["新分类(次)"] != r["原分类"]:
            target_pids.add(r["编号"])

    print(f"目标论文: {len(target_pids)} 条 (AI次分类!=原分类, 排除已纠正)")

    with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
        metadata = {r["编号"]: r for r in csv.DictReader(f)}

    old_classifications = {r["编号"]: r for r in candidates}

    papers = []
    for pid in sorted(target_pids, key=int):
        meta = metadata.get(pid)
        old = old_classifications.get(pid)
        if meta and old:
            papers.append({
                "pid": pid,
                "title": meta["题目"],
                "institution": meta["作者机构"],
                "orig_cls": old["原分类"],
                "old_main": old["新分类(主)"],
                "old_main_prob": old["主分类概率"],
                "old_sec": old["新分类(次)"],
                "old_sec_prob": old["次分类概率"],
            })
    return papers


def main():
    env = load_env()
    api_key = env.get("DASHSCOPE_API_KEY", "")
    base_url = env.get("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    if not api_key:
        print("❌ 未找到 DASHSCOPE_API_KEY，请检查 .env 文件")
        sys.exit(1)

    papers = load_17_papers()
    print(f"共 {len(papers)} 篇论文待验证\n", flush=True)

    results = []

    def process(paper):
        r = call_api(paper["title"], paper["institution"], api_key, base_url)
        if r:
            result = {
                **paper,
                "new_main": r.get("主分类"),
                "new_main_prob": r.get("主分类概率"),
                "new_sec": r.get("次分类"),
                "new_sec_prob": r.get("次分类概率"),
            }
            print(f"  ✓ PID {paper['pid']}: {r.get('主分类')}({r.get('主分类概率')})", flush=True)
            return result
        else:
            return {**paper, "new_main": None, "new_main_prob": None, "new_sec": None, "new_sec_prob": None}

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(process, p): p for p in papers}
        for future in as_completed(futures):
            results.append(future.result())

    # 对比分析
    print("\n" + "=" * 110)
    print(f"{'PID':<6}{'题目':<32}{'原分类':<12}{'旧AI主':<12}{'新AI主':<12}{'变化':<6}{'与原一致?'}")
    print("-" * 110)

    changed = 0
    same_as_orig_new = 0
    same_as_orig_old = 0

    for r in sorted(results, key=lambda x: int(x["pid"])):
        title_short = r["title"][:30]
        new_main = r.get("new_main") or "?"
        old_main = r["old_main"]
        orig = r["orig_cls"]

        is_changed = "→变" if new_main != old_main else " 同"
        if new_main != old_main:
            changed += 1

        match_orig = "✓" if new_main == orig else "✗"
        if new_main == orig:
            same_as_orig_new += 1
        if old_main == orig:
            same_as_orig_old += 1

        print(f"{r['pid']:<6}{title_short:<32}{orig:<12}{old_main:<12}{new_main:<12}{is_changed:<6}{match_orig}")

    print("-" * 110)
    print(f"\n=== 统计 ===")
    print(f"共 {len(results)} 篇")
    print(f"旧 prompt: AI主分类==原分类: {same_as_orig_old}/{len(results)} ({same_as_orig_old/len(results)*100:.0f}%)")
    print(f"新 prompt: AI主分类==原分类: {same_as_orig_new}/{len(results)} ({same_as_orig_new/len(results)*100:.0f}%)")
    print(f"新旧 AI 主分类不同: {changed}/{len(results)} ({changed/len(results)*100:.0f}%)")

    # 分组统计
    reverted = [r for r in results if r.get("new_main") and r["new_main"] == r["orig_cls"] and r["old_main"] != r["orig_cls"]]
    still_changed = [r for r in results if r.get("new_main") and r["new_main"] != r["orig_cls"] and r["old_main"] != r["orig_cls"]]
    newly_changed = [r for r in results if r.get("new_main") and r["new_main"] != r["orig_cls"] and r["old_main"] == r["orig_cls"]]

    if reverted:
        print(f"\n=== 新 AI 回归原分类（改进有效）: {len(reverted)} 条 ===")
        for r in reverted:
            print(f"  PID {r['pid']}: {r['title'][:40]}")
            print(f"    原={r['orig_cls']}  旧AI={r['old_main']}  →  新AI={r.get('new_main')}({r.get('new_main_prob')})")

    if still_changed:
        print(f"\n=== 新旧 AI 都改变了原分类（需专家审核）: {len(still_changed)} 条 ===")
        for r in still_changed:
            print(f"  PID {r['pid']}: {r['title'][:40]}")
            print(f"    原={r['orig_cls']}  旧AI={r['old_main']}({r['old_main_prob']})  新AI={r.get('new_main')}({r.get('new_main_prob')})")

    if newly_changed:
        print(f"\n=== 新 prompt 反而改变了旧 prompt 正确的分类（退化）: {len(newly_changed)} 条 ===")
        for r in newly_changed:
            print(f"  PID {r['pid']}: {r['title'][:40]}")
            print(f"    原={r['orig_cls']}  旧AI={r['old_main']}  →  新AI={r.get('new_main')}({r.get('new_main_prob')})")

    # 保存
    output_path = Path("results/e2-top102/verify_17_reclassify_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存到: {output_path}")


if __name__ == "__main__":
    main()
