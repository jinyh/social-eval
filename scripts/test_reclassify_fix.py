#!/usr/bin/env python3
"""
测试修复后的重分类脚本：对3篇论文测试概率约束是否生效。
"""

import csv, http.client, json, ssl, time, sys
from pathlib import Path

CSV_PATH = Path("results/sandakan-new-metadata.csv")
MERGED_META_PATH = Path("results/merged-metadata.csv")
AI_CLASS_PATH = Path("results/sandakan-ai-classification.json")
EVAL_DIR = Path("results/fullevaluation/round2")

MODEL = "qwen3.7-max"
TEMPERATURE = 0.3
TIMEOUT = 60

CATEGORY_LIST = "、".join([
    "民商法学", "刑法学", "宪法学与行政法学", "诉讼法学", "法学理论",
    "环境与资源保护法学", "国际法学", "经济法学", "知识产权法学",
    "法律史", "党内法规学",
])

METHODOLOGY_KEYWORDS = [
    "教义学", "实证研究", "实证分析", "解释论", "比较研究", "比较法",
    "法经济学", "法经济分析", "法社会学", "社科法学", "法教义学",
    "类型化", "体系化", "方法论", "立法论", "法政策学", "法政策",
    "反思", "重构", "完善", "改进", "优化",
    "法治化", "现代化", "中国化", "本土化",
]

PROMPT = """\
你是一位法学学科分类专家。根据论文标题、作者机构、关键词和内容摘要，判断该论文所属的法学二级学科。

可选学科（11个）：{categories}

## 分类规则

1. **劳动法、社会保障法方向**归入"民商法学"。
2. **标题含民法核心概念**（赔偿、债务、信托、权利体系、诚实信用、公序良俗、监护、占有、夫妻、财产私法保护、自甘冒险）→ 归入"民商法学"。
3. **标题含刑法教义学概念**（具体罪名、被害人、自陷风险、注意义务、违法性认识错误）→ 归入"刑法学"。
4. **标题含宪法概念**（合宪性、基本权利）→ 归入"宪法学与行政法学"。
5. **标题含涉外/准据法** → 归入"国际法学"。
6. **标题偏法哲学/认识论**（证据客观性、理由模式、功能限度）→ 归入"法学理论"。
7. **区分原则**：看论文的**核心贡献**属于哪个学科，而非背景关键词。
   - **跨域研究背景**：标题含"…视野下""…协动""…交叉"等跨域信号时，若同时含"理论构成""体系构造""教义学分析"等理论建构词，以论文**核心论点所属学科的方法论**归类，而非应用领域。例如：在环境法背景下用民法教义学构建赔偿理论 → 民商法学。
8. **学科惯性原则**：除非有压倒性证据，否则不应轻易改变原始学科归属。
9. **关键词使用原则**：实质性概念（如"罪刑法定""物权"）是强信号；方法论术语（如"教义学""实证研究""解释论"）不指示学科。
10. **摘要优先原则**：当标题和关键词存在歧义时，以摘要描述的论文核心贡献为准。摘要中提到的具体研究对象（如"合同效力""犯罪构成""行政处罚"）比标题中的抽象术语更能反映学科归属。

## 待分类论文

论文标题：{title}
作者机构：{institution}
关键词：{keywords}
内容摘要：{summary}

返回 JSON（**关键约束：主分类概率 + 次分类概率 必须 = 1.0**）：
{{"主分类": "学科名", "主分类概率": 0.xx, "次分类": "学科名或留空", "次分类概率": 0.xx, "理由": "一句话说明"}}

**概率说明**：
- 主分类概率 + 次分类概率 = 1.0（严格相等）
- 概率表示该学科在分类中的占比，不是独立置信度
- 如果只有一个明确学科，次分类留空，次分类概率=0，主分类概率=1.0
- 示例：{{"主分类": "民商法学", "主分类概率": 0.85, "次分类": "经济法学", "次分类概率": 0.15, "理由": "..."}}
"""


def load_env():
    env = {}
    for line in Path(".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def filter_keywords(raw):
    if not raw:
        return "(无)"
    kws = [kw.strip() for kw in raw.replace(" ", ";").split(";") if kw.strip()]
    filtered = [kw for kw in kws if not any(mk in kw for mk in METHODOLOGY_KEYWORDS)]
    return "; ".join(filtered) if filtered else "; ".join(kws)


def get_summary(pid):
    path = EVAL_DIR / f"paper-{pid}.json"
    if not path.exists():
        return "(无摘要)"
    try:
        with open(path, "r") as f:
            d = json.load(f)
        dims = d.get("dimensions", {})
        parts = []
        for dim_name in ["problem_originality", "analytical_framework"]:
            dim = dims.get(dim_name, {})
            raw = dim.get("raw_outputs", {})
            for model_name, model_output in raw.items():
                if isinstance(model_output, dict):
                    for key in ["initial_evaluation", "revision_rationale"]:
                        if key in model_output and isinstance(model_output[key], str):
                            parts.append(model_output[key][:400])
                            break
                break
        return " | ".join(parts)[:600] if parts else "(无摘要)"
    except:
        return "(无摘要)"


def call_api(title, institution, keywords, summary, api_key, base_url):
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT.format(
            categories=CATEGORY_LIST, title=title, institution=institution,
            keywords=keywords, summary=summary)}],
        "response_format": {"type": "json_object"},
        "temperature": TEMPERATURE,
    })
    host = base_url.replace("https://", "").split("/")[0]
    path_prefix = "/" + "/".join(base_url.replace("https://", "").split("/")[1:])
    ctx = ssl.create_default_context()

    try:
        conn = http.client.HTTPSConnection(host, 443, timeout=TIMEOUT, context=ctx)
        conn.request("POST", f"{path_prefix}/chat/completions", body=payload,
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
        resp = conn.getresponse()
        data = json.loads(resp.read().decode("utf-8"))
        conn.close()
        return json.loads(data["choices"][0]["message"]["content"])
    except Exception as e:
        print(f"API 错误: {e}")
        return None


def main():
    env = load_env()
    api_key = env.get("DASHSCOPE_API_KEY", "")
    base_url = env.get("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    if not api_key:
        print("❌ 未找到 DASHSCOPE_API_KEY")
        sys.exit(1)

    # Load data
    with open(MERGED_META_PATH, "r", encoding="utf-8-sig") as f:
        merged_meta = {r["编号"]: r for r in csv.DictReader(f)}

    # 测试5篇论文：3篇之前概率和>1的 + 2篇之前有显著次分类的
    test_pids = ["1", "8", "23", "1236", "152"]

    print("测试修复后的概率约束（5篇论文）\n")

    for pid in test_pids:
        m = merged_meta.get(pid, {})
        title = m.get("题目", "")
        institution = m.get("作者机构", "")
        keywords = filter_keywords(m.get("主题词", ""))
        summary = get_summary(pid)

        print(f"PID {pid}: {title[:40]}...")

        r = call_api(title, institution, keywords, summary, api_key, base_url)
        if r:
            main_prob = r.get("主分类概率", 0) or 0
            sec_prob = r.get("次分类概率", 0) or 0
            prob_sum = main_prob + sec_prob

            print(f"  主分类: {r.get('主分类', '')} (概率: {main_prob:.2f})")
            print(f"  次分类: {r.get('次分类', '')} (概率: {sec_prob:.2f})")
            print(f"  概率和: {prob_sum:.2f}")

            if abs(prob_sum - 1.0) < 0.02:
                print(f"  ✓ 概率和正常")
            else:
                print(f"  ⚠️  概率和异常")
        else:
            print("  ❌ API 调用失败")

        print()
        time.sleep(1)  # 避免限流


if __name__ == "__main__":
    main()
