#!/usr/bin/env python3
"""
用新 prompt 重跑低置信度论文（主分类概率 < 0.90），对比新旧结果。
8 并发，纯标准库。

用法: python3.12 scripts/reclassify_low_confidence.py
"""

import csv, http.client, json, ssl, time, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

CSV_PATH = Path("results/sandakan-new-metadata.csv")
THRESHOLD = 0.90
CONCURRENCY = 8
MODEL = "qwen3.7-max"
TEMPERATURE = 0.3
TIMEOUT = 60
MAX_RETRIES = 2

CATEGORY_LIST = "、".join([
    "民商法学", "刑法学", "宪法学与行政法学", "诉讼法学", "法学理论",
    "环境与资源保护法学", "国际法学", "经济法学", "知识产权法学",
    "法律史", "党内法规学",
])

PROMPT = """\
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
    env = {}
    for line in Path(".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def call_api(title, institution, api_key, base_url):
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT.format(
            categories=CATEGORY_LIST, title=title, institution=institution
        )}],
        "response_format": {"type": "json_object"},
        "temperature": TEMPERATURE,
    })
    host = base_url.replace("https://", "").split("/")[0]
    path_prefix = "/" + "/".join(base_url.replace("https://", "").split("/")[1:])
    ctx = ssl.create_default_context()
    for attempt in range(MAX_RETRIES + 1):
        try:
            conn = http.client.HTTPSConnection(host, 443, timeout=TIMEOUT, context=ctx)
            conn.request("POST", f"{path_prefix}/chat/completions", body=payload,
                        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
            resp = conn.getresponse()
            data = json.loads(resp.read().decode("utf-8"))
            conn.close()
            return json.loads(data["choices"][0]["message"]["content"])
        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(2)
                continue
            return None


def main():
    env = load_env()
    api_key = env.get("DASHSCOPE_API_KEY", "")
    base_url = env.get("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    if not api_key:
        print("❌ 未找到 DASHSCOPE_API_KEY"); sys.exit(1)

    with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
        all_rows = list(csv.DictReader(f))

    papers = []
    for r in all_rows:
        try:
            prob = float(r["主分类概率"])
        except (ValueError, KeyError):
            continue
        if prob < THRESHOLD:
            papers.append(r)

    print(f"筛选条件: 主分类概率 < {THRESHOLD}")
    print(f"待重跑: {len(papers)} 条")
    print(f"并发: {CONCURRENCY}\n", flush=True)

    results = []
    completed = 0
    changed = 0
    failed = 0

    def process(paper):
        r = call_api(paper["题目"], paper["作者机构"], api_key, base_url)
        if r:
            return {
                "pid": paper["编号"], "title": paper["题目"],
                "orig": paper["原分类"], "expert": paper.get("专家分类", ""),
                "old_main": paper["主分类"], "old_prob": paper["主分类概率"],
                "new_main": r.get("主分类", ""), "new_prob": r.get("主分类概率"),
                "new_sec": r.get("次分类"), "new_sec_prob": r.get("次分类概率"),
                "changed": paper["主分类"] != r.get("主分类", ""),
            }
        return {"pid": paper["编号"], "title": paper["题目"], "failed": True}

    start_time = time.time()

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futs = [ex.submit(process, p) for p in papers]
        for f in as_completed(futs):
            r = f.result()
            results.append(r)
            completed += 1
            if r.get("failed"):
                failed += 1
            elif r["changed"]:
                changed += 1

            if completed % 50 == 0 or completed == len(papers):
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                print(f"  进度: {completed}/{len(papers)} "
                      f"({changed} changed, {failed} failed, {rate:.1f}/s)",
                      flush=True)

    elapsed = time.time() - start_time
    success = [r for r in results if not r.get("failed")]
    changes = [r for r in success if r["changed"]]

    print(f"\n{'='*80}")
    print(f"完成: {completed}/{len(papers)} ({failed} failed)")
    print(f"耗时: {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print(f"分类变化: {len(changes)}/{len(success)} ({len(changes)/len(success)*100:.1f}%)")

    if changes:
        print(f"\n{'='*80}")
        print(f"分类变化的论文 ({len(changes)} 条):")
        print(f"{'='*80}")
        print(f"{'PID':<6}{'题目':<30}{'原分类':<12}{'旧AI':<12}{'新AI':<12}{'新P':<5}{'专家'}")
        print("-" * 95)
        for r in sorted(changes, key=lambda x: int(x["pid"])):
            expert = r.get("expert") or "-"
            print(f"{r['pid']:<6}{r['title'][:28]:<30}{r['orig']:<12}{r['old_main']:<12}{r['new_main']:<12}{r['new_prob']:<5}{expert}")

    output_path = Path("results/e2-top102/reclassify_low_confidence_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(success, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果: {output_path}")


if __name__ == "__main__":
    main()
