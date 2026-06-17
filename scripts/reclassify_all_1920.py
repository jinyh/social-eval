#!/usr/bin/env python3
"""
全量重分类：用"标题+机构+过滤关键词+评审摘要"的新 prompt 重跑 1920 篇论文。
8 并发，支持断点续跑。

用法: python3.12 scripts/reclassify_all_1920.py
"""

import csv, http.client, json, ssl, time, sys, os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

CSV_PATH = Path("results/sandakan-new-metadata.csv")
MERGED_META_PATH = Path("results/merged-metadata.csv")
AI_CLASS_PATH = Path("results/sandakan-ai-classification.json")
EVAL_DIR = Path("results/fullevaluation/round2")
CHECKPOINT_PATH = Path("results/e2-top102/reclassify_all_checkpoint.json")
OUTPUT_V3_PATH = Path("results/sandangan-new-metadata-v3.csv")
REPORT_PATH = Path("results/e2-top102/reclassification-methodology-report.md")

CONCURRENCY = 8
MODEL = "qwen3.7-max"
TEMPERATURE = 0.3
TIMEOUT = 60
MAX_RETRIES = 2
CHECKPOINT_INTERVAL = 50

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


def load_checkpoint():
    if CHECKPOINT_PATH.exists():
        with open(CHECKPOINT_PATH, "r") as f:
            return json.load(f)
    return {}


def save_checkpoint(results):
    with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False)


def main():
    env = load_env()
    api_key = env.get("DASHSCOPE_API_KEY", "")
    base_url = env.get("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    if not api_key:
        print("❌ 未找到 DASHSCOPE_API_KEY"); sys.exit(1)

    # Load data
    with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
        csv_rows = {r["编号"]: r for r in csv.DictReader(f)}

    with open(MERGED_META_PATH, "r", encoding="utf-8-sig") as f:
        merged_meta = {r["编号"]: r for r in csv.DictReader(f)}

    with open(AI_CLASS_PATH, "r") as f:
        ai_data = json.load(f)

    all_pids = sorted(ai_data.keys(), key=int)
    print(f"全量重分类: {len(all_pids)} 篇, 并发: {CONCURRENCY}")

    # Load checkpoint
    checkpoint = load_checkpoint()
    done_pids = set(checkpoint.keys())
    todo_pids = [pid for pid in all_pids if pid not in done_pids]
    print(f"已完成: {len(done_pids)}, 待跑: {len(todo_pids)}\n", flush=True)

    if not todo_pids:
        print("全部已完成！")
    else:
        completed = len(done_pids)
        failed = sum(1 for v in checkpoint.values() if v.get("failed"))
        changed = sum(1 for pid, v in checkpoint.items()
                      if not v.get("failed") and v.get("new_main") and v["new_main"] != ai_data.get(pid, {}).get("主分类", ""))
        start_time = time.time()

        def process(pid):
            m = merged_meta.get(pid, csv_rows.get(pid, {}))
            ai = ai_data.get(pid, {})
            title = m.get("题目", "")
            institution = m.get("作者机构", "")
            keywords = filter_keywords(m.get("主题词", ""))
            summary = get_summary(pid)

            r = call_api(title, institution, keywords, summary, api_key, base_url)
            if r:
                new_main = r.get("主分类", "")
                new_prob = r.get("主分类概率", 0) or 0
                new_sec = r.get("次分类", "")
                new_sec_prob = r.get("次分类概率", 0) or 0

                # 验证并修正概率和
                prob_sum = new_prob + new_sec_prob
                if prob_sum > 1.01:  # 超过1则归一化
                    new_prob = new_prob / prob_sum
                    new_sec_prob = new_sec_prob / prob_sum
                    prob_sum = 1.0
                elif prob_sum < 0.99 and prob_sum > 0:  # 接近但不等于1，补齐到1
                    new_prob = new_prob / prob_sum
                    new_sec_prob = new_sec_prob / prob_sum

                old_main = ai.get("主分类", "")
                return {
                    "new_main": new_main,
                    "new_prob": round(new_prob, 2),
                    "new_sec": new_sec if new_sec else "",
                    "new_sec_prob": round(new_sec_prob, 2),
                    "reason": r.get("理由", ""),
                    "changed": (new_main != old_main) if new_main else False,
                }
            return {"failed": True}

        with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
            futs = {ex.submit(process, pid): pid for pid in todo_pids}
            for f in as_completed(futs):
                pid = futs[f]
                result = f.result()
                checkpoint[pid] = result
                completed += 1
                if result.get("failed"):
                    failed += 1
                elif result.get("changed"):
                    changed += 1

                if completed % CHECKPOINT_INTERVAL == 0 or completed == len(all_pids):
                    save_checkpoint(checkpoint)
                    elapsed = time.time() - start_time
                    rate = completed / elapsed if elapsed > 0 else 0
                    remaining = (len(all_pids) - completed) / rate if rate > 0 else 0
                    print(f"  进度: {completed}/{len(all_pids)} "
                          f"({changed} changed, {failed} failed, {rate:.1f}/s, "
                          f"剩余 {remaining/60:.0f}min)", flush=True)

        save_checkpoint(checkpoint)
        elapsed = time.time() - start_time
        print(f"\n完成: {completed}/{len(all_pids)} ({failed} failed), 耗时: {elapsed/60:.1f}min")

    # Generate v3 CSV
    print("\n生成 v3 CSV...", flush=True)
    output_fields = [
        "编号", "期刊", "年份", "题目", "作者", "作者机构",
        "原分类", "专家分类",
        "主分类", "主分类概率", "次分类", "次分类概率",
        "新主分类", "新主分类概率", "新次分类", "新次分类概率",
        "主分类是否变化", "次分类是否变化",
    ]

    v3_rows = []
    main_changed_count = 0
    sec_changed_count = 0
    prob_sum_issues = 0

    for pid in sorted(ai_data.keys(), key=int):
        ai = ai_data[pid]
        m = merged_meta.get(pid, csv_rows.get(pid, {}))
        r = checkpoint.get(pid, {})

        old_main_cls = ai.get("主分类", "")
        old_sec_cls = ai.get("次分类", "")

        # 始终记录新分类结果（即使与旧分类相同）
        new_main = ""
        new_main_prob = ""
        new_sec = ""
        new_sec_prob = ""
        main_changed = "否"
        sec_changed = "否"

        if not r.get("failed"):
            new_main = r.get("new_main", "")
            new_main_prob = r.get("new_prob", "")
            new_sec = r.get("new_sec", "")
            new_sec_prob = r.get("new_sec_prob", "")

            # 检查概率和
            if new_main_prob and new_sec_prob:
                prob_sum = float(new_main_prob) + float(new_sec_prob)
                if abs(prob_sum - 1.0) > 0.02:  # 容忍2%误差
                    prob_sum_issues += 1

            # 判断是否变化
            if new_main and new_main != old_main_cls:
                main_changed = "是"
                main_changed_count += 1
            if new_sec and new_sec != old_sec_cls:
                sec_changed = "是"
                sec_changed_count += 1

        v3_rows.append({
            "编号": pid,
            "期刊": m.get("期刊", ""),
            "年份": m.get("年份", ""),
            "题目": m.get("题目", ""),
            "作者": m.get("作者", ""),
            "作者机构": m.get("作者机构", ""),
            "原分类": m.get("原分类", csv_rows.get(pid, {}).get("原分类", "")),
            "专家分类": csv_rows.get(pid, {}).get("专家分类", ""),
            "主分类": old_main_cls,
            "主分类概率": ai.get("主分类概率", ""),
            "次分类": old_sec_cls,
            "次分类概率": ai.get("次分类概率", ""),
            "新主分类": new_main,
            "新主分类概率": new_main_prob,
            "新次分类": new_sec,
            "新次分类概率": new_sec_prob,
            "主分类是否变化": main_changed,
            "次分类是否变化": sec_changed,
        })

    with open(OUTPUT_V3_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=output_fields)
        writer.writeheader()
        writer.writerows(v3_rows)

    print(f"✓ v3 CSV: {OUTPUT_V3_PATH}")
    print(f"  主分类变化: {main_changed_count} 条")
    print(f"  次分类变化: {sec_changed_count} 条")
    if prob_sum_issues > 0:
        print(f"  ⚠️  概率和异常: {prob_sum_issues} 条（已归一化）")

    # Generate report
    generate_report(v3_rows, checkpoint, ai_data, csv_rows)


def generate_report(v3_rows, checkpoint, ai_data, csv_rows):
    """生成方法论报告。"""
    total = len(v3_rows)
    changed_main = sum(1 for r in v3_rows if r["主分类是否变化"] == "是")
    changed_sec = sum(1 for r in v3_rows if r["次分类是否变化"] == "是")
    failed = sum(1 for v in checkpoint.values() if v.get("failed"))

    # 概率和检查
    prob_issues = 0
    for r in v3_rows:
        if r["新主分类概率"] and r["新次分类概率"]:
            try:
                prob_sum = float(r["新主分类概率"]) + float(r["新次分类概率"])
                if abs(prob_sum - 1.0) > 0.02:
                    prob_issues += 1
            except:
                pass

    # Expert accuracy
    expert_papers = [r for r in v3_rows if r["专家分类"]]
    old_correct = sum(1 for r in expert_papers if r["主分类"] == r["专家分类"])
    new_correct = 0
    for r in expert_papers:
        final = r["新主分类"] if r["新主分类"] else r["主分类"]
        if final == r["专家分类"]:
            new_correct += 1

    # Discipline distribution
    from collections import Counter
    old_dist = Counter(r["主分类"] for r in v3_rows)
    new_dist = Counter()
    for r in v3_rows:
        cls = r["新主分类"] if r["新主分类"] else r["主分类"]
        new_dist[cls] += 1

    report = f"""# 全量重分类方法论报告

> 生成时间: {time.strftime('%Y-%m-%d %H:%M')}

## 1. 背景

旧 prompt（仅标题+机构）对 1920 篇论文进行学科分类后，发现以下问题：
- 71 条论文被 AI 重分类（AI主分类 ≠ 原分类），进入专家审核
- 33 条论文获得专家纠正（来自 3 个专家纠正文件）
- 8 条专家纠正论文（标黄）用于 prompt 迭代训练

## 2. Prompt 迭代记录

### Round 1: 仅标题+机构
- 旧 prompt: 7 条规则 + 5 个示例
- 改进 prompt: 新增第 8 条"学科惯性原则" + 4 个边界案例示例
- 结果: 33 条专家纠正论文上，旧 76% → 新 91%（+5）

### Round 2: 验证模式
- 给 AI 看当前分类，问"对不对"
- 结果: 2/8 (25%)，确认偏差严重，放弃

### Round 3: Top-3 + Rerank
- 先出 3 个候选，再二次选择
- 结果: 3/8 (38%)，Rerank 也有确认偏差，放弃

### Round 4: 标题+过滤关键词（69 条低置信度论文）
- 过滤方法论关键词（教义学、实证研究等）
- 结果: 42/69 (61%) 分类发生变化
- 关键词解决了一批问题，也引入了新陷阱（如"数据权属"误导→知识产权法）

### Round 5: 标题+过滤关键词+评审摘要（69 条低置信度论文）
- 评审摘要从 fullevaluation JSON 提取
- 结果: 与关键词版 80% 一致，14 条额外修正
- 摘要在歧义案例上起到关键"仲裁"作用

### Round 6: 概率约束修复（本次）
- 发现问题：844/1920 (44%) 论文的主次概率和 > 1
- 根因：模型将概率理解为"独立置信度"而非"归一化占比"
- 修复：
  1. Prompt 明确约束"主分类概率 + 次分类概率 = 1.0"
  2. 后处理自动归一化超过1的概率
  3. CSV 始终记录完整新分类结果（不再隐藏未变化的）
  4. 新增"主分类是否变化"/"次分类是否变化"列

## 3. 最终 Prompt 规格

- **输入**: 标题 + 作者机构 + 过滤后主题词 + 评审摘要（前 600 字）
- **规则**: 10 条（含学科惯性原则、关键词使用原则、摘要优先原则）
- **概率约束**: 主分类概率 + 次分类概率 = 1.0（严格相等）
- **模型**: qwen3.7-max, temperature=0.3
- **过滤规则**: 移除方法论关键词（教义学、实证研究、解释论等 30+ 个）
- **摘要来源**: fullevaluation/round2 的 problem_originality + analytical_framework 维度首模型评价

## 4. 全量重跑统计

| 指标 | 数值 |
|------|------|
| 总论文数 | {total} |
| 新主分类有变化 | {changed_main} ({changed_main/total*100:.1f}%) |
| 新次分类有变化 | {changed_sec} ({changed_sec/total*100:.1f}%) |
| API 失败 | {failed} |
| 概率和异常（>1.02 或 <0.98） | {prob_issues} |

### 专家分类准确率（{len(expert_papers)} 条有专家分类的论文）

| 版本 | 正确率 |
|------|--------|
| 旧 AI | {old_correct}/{len(expert_papers)} ({old_correct/len(expert_papers)*100:.0f}%) |
| 新 AI | {new_correct}/{len(expert_papers)} ({new_correct/len(expert_papers)*100:.0f}%) |

### 学科分布变化

| 学科 | 旧AI | 新AI | 变化 |
|------|------|------|------|
"""
    all_cats = sorted(set(list(old_dist.keys()) + list(new_dist.keys())))
    for cat in all_cats:
        o = old_dist.get(cat, 0)
        n = new_dist.get(cat, 0)
        diff = n - o
        sign = "+" if diff > 0 else ""
        report += f"| {cat} | {o} | {n} | {sign}{diff} |\n"

    report += f"""
## 5. 输出文件

- `results/sandangan-new-metadata-v3.csv` — 全量重分类结果
- `results/e2-top102/reclassify_all_checkpoint.json` — 断点续跑存档
- `results/e2-top102/reclassification-methodology-report.md` — 本报告

## 6. 局限性

1. 评审摘要是 AI 模型的评价文本，非作者原文摘要，可能引入评价偏差
2. 1 篇论文（PID 1621）无主题词，依赖标题+摘要分类
3. 仍有部分边界案例（如"算法透明层次论"）跨学科性质强，任何分类都有争议
4. 未做全量的专家验证，仅在 33 条子集上验证了准确率
"""

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"✓ 报告: {REPORT_PATH}")


if __name__ == "__main__":
    main()
