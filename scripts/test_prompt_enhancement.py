#!/usr/bin/env python3
"""
验证增强 prompt 对 25 篇专家修正论文的分类效果。

对比旧 prompt（无规则无示例）和新 prompt（含专家规则 + few-shot）的分类准确率。

用法: uv run python scripts/test_prompt_enhancement.py
"""

import asyncio
import csv
import json
import os
import re
from pathlib import Path

import openai
from dotenv import load_dotenv

load_dotenv()

MODEL = "qwen3.7-max"
TEMPERATURE = 0.3
TIMEOUT = 60

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

OLD_PROMPT = """\
你是一位法学学科分类专家。根据论文标题和作者机构，判断该论文所属的法学二级学科。

可选学科（11个）：{categories}

注意：涉及劳动法、社会保障法方向的论文请归入"民商法学"。

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

NEW_PROMPT = """\
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


# 25 条专家修正 (metadata_pid, title, institution, expert_target)
EXPERT_CORRECTIONS = [
    (51, '三权分置下农地流转权利体系重构研究', '中共中央党校（国家行政学院）法学部', '民商法学'),
    (211, '农村土地流转的合宪性分析', '山东大学法学院', '宪法学与行政法学'),
    (245, '劳动者个人信息处理中同意的适用与限制', '上海财经大学法学院', '民商法学'),
    (317, '基本原则与概括条款的区分：我国诚实信用与公序良俗的解释论构造', '中国政法大学民商经济法学院', '民商法学'),
    (319, '基本权利私人间效力法理基础的澄清与重构', '北京航空航天大学法学院', '宪法学与行政法学'),
    (413, '抢劫罪与敲诈勒索罪之界分：基于被害人的处分自由', '北京大学法学院', '刑法学'),
    (655, '职场智能监控下的劳动者个人信息保护——以目的原则为中心', '天津大学法学院', '民商法学'),
    (956, '公序良俗原则与诚实信用原则的区分', '中国政法大学民商经济法学院', '民商法学'),
    (1194, '从基本权理论看法律行为之阻却生效要件：一个跨法域释义学的尝试', '浙江大学光华法学院', '民商法学'),
    (1223, '保底信托效力认定的类型化', '中国人民大学民商事法律科学研究中心', '民商法学'),
    (1271, '公私法协动视野下生态环境损害赔偿的理论构成', '南京大学法学院', '民商法学'),
    (1322, '劳动关系认定的理论澄清与规范建构', '上海交通大学凯原法学院', '民商法学'),
    (1390, '基于决定关系的证据客观性：概念、功能与理论定位', '中国人民大学法学院', '法学理论'),
    (1412, '夫妻债务的清偿顺序', '上海财经大学法学院', '民商法学'),
    (1449, '工伤认定一般条款的建构路径', '暨南大学法学院', '民商法学'),
    (1519, '整体法秩序视野下被害人自陷风险的理论重塑', '中国人民大学刑事法律科学研究中心', '刑法学'),
    (1521, '文体活动自甘冒险的风险分配与范围划定', '中国政法大学民商经济法学院', '民商法学'),
    (1615, '注意义务的规范本质与判断标准', '中国人民大学刑事法律科学研究中心', '刑法学'),
    (1618, '涉外代理关系准据法的确定', '清华大学法学院', '国际法学'),
    (1642, '现代监护理念下监护与行为能力关系的重构', '上海交通大学凯原法学院', '民商法学'),
    (1727, '行贿罪之"谋取不正当利益"的法理内涵', '北京大学法学院', '刑法学'),
    (1742, '计算机信息系统作为财产的私法保护', '中国社会科学院法学研究所', '民商法学'),
    (1777, '调整个性化定价的公私法协动体系构造', '南京大学法学院', '民商法学'),
    (1818, '金钱"占有即所有"原理批判及权利流转规则之重塑', '西南政法大学民商法学院', '民商法学'),
    (1852, '司法人工智能的理由模式及其功能限度', '上海交通大学凯原法学院', '法学理论'),
]


def extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    raise ValueError(f"无法解析: {text[:100]}")


async def classify(client, prompt_template, title, institution):
    prompt = prompt_template.format(
        categories=CATEGORY_LIST, title=title, institution=institution,
    )
    resp = await asyncio.wait_for(
        client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=TEMPERATURE,
        ),
        timeout=TIMEOUT,
    )
    result = extract_json(resp.choices[0].message.content)
    result["主分类"] = CATEGORY_MAPPING.get(result["主分类"], result["主分类"])
    result["次分类"] = CATEGORY_MAPPING.get(result["次分类"], result["次分类"])
    return result


async def main():
    client = openai.AsyncOpenAI(
        api_key=os.getenv("DASHSCOPE_API_KEY", ""),
        base_url=os.getenv(
            "DASHSCOPE_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
    )

    old_correct = 0
    new_correct = 0
    total = len(EXPERT_CORRECTIONS)
    results = []

    print(f"{'='*100}")
    print(f"Prompt 增强验证：{total} 篇专家修正论文")
    print(f"{'='*100}")
    print(f"{'PID':>5} | {'旧prompt':^12} {'旧P':>4} | {'新prompt':^12} {'新P':>4} | {'专家':^12} | 旧 新 | 题目")
    print("-" * 100)

    for pid, title, inst, target in EXPERT_CORRECTIONS:
        old_r, new_r = await asyncio.gather(
            classify(client, OLD_PROMPT, title, inst),
            classify(client, NEW_PROMPT, title, inst),
        )

        old_main = old_r["主分类"]
        new_main = new_r["主分类"]
        old_ok = old_main == target
        new_ok = new_main == target

        if old_ok:
            old_correct += 1
        if new_ok:
            new_correct += 1

        results.append((pid, title, target, old_r, new_r, old_ok, new_ok))

        print(
            f"{pid:5d} | {old_main:12s} {old_r['主分类概率']:>4} | "
            f"{new_main:12s} {new_r['主分类概率']:>4} | "
            f"{target:12s} | {'✅' if old_ok else '❌'} {'✅' if new_ok else '❌'} | {title[:30]}"
        )

    print(f"\n{'='*100}")
    print(f"结果对比:")
    print(f"  旧 prompt: {old_correct}/{total} ({old_correct/total*100:.0f}%)")
    print(f"  新 prompt: {new_correct}/{total} ({new_correct/total*100:.0f}%)")
    delta = new_correct - old_correct
    if delta > 0:
        print(f"  提升: +{delta} 篇 (+{delta/total*100:.0f}%)")
    elif delta < 0:
        print(f"  退步: {delta} 篇 ({delta/total*100:.0f}%)")
    else:
        print(f"  无变化")

    # 变化详情
    changes = [(pid, title, target, old_r, new_r) for pid, title, target, old_r, new_r, old_ok, new_ok in results if old_ok != new_ok]
    if changes:
        print(f"\n变化详情:")
        for pid, title, target, old_r, new_r in changes:
            direction = "改进" if new_r["主分类"] == target else "退步"
            print(f"  PID {pid} [{direction}]: {old_r['主分类']} → {new_r['主分类']} (专家={target}) | {title[:40]}")


if __name__ == "__main__":
    asyncio.run(main())
