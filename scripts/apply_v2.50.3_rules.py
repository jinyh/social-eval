#!/usr/bin/env python3
"""
创建 v2.50.3 框架：在评分锚定表中直接加入负面模式降档

v2.50.2 的问题：
- 嵌入的降档规则放在子项评分之后、锚定表之前
- AI 逐项打分后直接用分数锚定到 excellent 档，跳过降档检查

v2.50.3 的策略：
- 直接修改评分锚定表的文本
- 在"确定分数"步骤中加入强制降档条件
- AI 在查表确定分档时必须同时检查负面模式
"""
import yaml
from pathlib import Path

# 问题创新性：保留前置扣分（已验证有效）
PROBLEM_ORIGINALITY_PREFIX = """【强制前置检查 - 负面模式扣分】

⚠️ 在进行任何评分之前，必须先完成以下负面模式检查。如果跳过此步骤，后续评分无效。

请逐项检查并记录扣分：

□ 检查1：新概念包装旧问题（扣 15-25 分）
  条件：论文引入新概念/新术语作为核心创新点，但未明确说明新概念相对既有概念的理论进步
  - 未说明任何优势 → 扣 25 分
  - 只说"填补空白"但未说明解释力提升 → 扣 20 分
  - 有部分说明但不充分 → 扣 15 分
  - 不满足条件 → 不扣分

□ 检查2：宏观介绍非深度分析（扣 15-20 分）
  条件：论文完成了体系介绍但未触及现实问题，无不同学者观点的交锋
  - 全文无任何学者观点交锋 → 扣 20 分
  - 有提及分歧但未展开 → 扣 15 分
  - 不满足条件 → 不扣分

□ 检查3：主题声明非研究问题（扣 20-30 分）
  条件：全文主要是阐释既定立场，无可争辩的法学争点
  - 全文无任何问题句 → 扣 30 分
  - 有问题句但实质是政策倡导 → 扣 20 分
  - 不满足条件 → 不扣分

扣分合计 = ___分（记录在 score_rationale 中）
扣分后的分数不得低于 30 分。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
现在开始正式评分（最终分数 = 正式评分 - 扣分合计）：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""


def apply_v2_50_3_rules():
    """创建 v2.50.3 框架"""

    source_path = Path("configs/frameworks/law-v2.47-20260511.yaml")
    target_path = Path("configs/frameworks/law-v2.50.3-20260514.yaml")

    with open(source_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # 1. 更新 metadata
    config['metadata']['name'] = "法学评价框架 v2.50.3（锚定表内嵌负面模式降档）"
    config['metadata']['version'] = "2.50.3"
    config['metadata']['created'] = "2026-05-14"
    config['metadata']['previous_version'] = "2.50.2"
    config['metadata']['source'] = "v2.47 + 锚定表内嵌负面模式降档"
    config['metadata']['changelog'] = """v2.50.3 变化（2026-05-14，锚定表内嵌负面模式降档）：
【目标】修复 v2.50.2 中分析框架维度降档规则被跳过的问题。

核心变化：
1. 问题创新性：保留前置扣分（已验证有效）
2. 分析框架：将负面模式降档条件直接写入"确定分数"步骤的锚定表中
3. 结论可接受性：将负面模式降档条件直接写入"确定分数"步骤的锚定表中
4. 关键改进：不再在子项评分后加降档检查，而是在锚定表查表时强制检查

设计原理：
- v2.50.2 证明：AI 逐项打分后直接查表锚定，跳过中间的降档检查
- 新策略：在锚定表本身中加入"如果存在负面模式则强制降档"的条件
- AI 在"确定分数"步骤查表时必须同时检查负面模式"""

    # 2. 修改 prompt_template
    dimensions = config['dimensions']

    for dim in dimensions:
        if dim['key'] == 'problem_originality':
            dim['prompt_template'] = PROBLEM_ORIGINALITY_PREFIX + dim['prompt_template']
            print(f"  ✅ 问题创新性：保留前置扣分")

        elif dim['key'] == 'analytical_framework':
            pt = dim['prompt_template']

            # 在锚定表之后、上限规则之前插入强制降档
            old_anchor = "【上限规则】："
            new_anchor = """【负面模式强制降档 - 优先于上限规则执行】：
在查表确定分档后，必须检查以下负面模式。如果触发，无论上面的分档结果如何，强制降档：

4. 口号式呼吁：论文中"应当""必须""需要完善/加强"等规范性表述≥5处，且对应的具体制度方案不足
   → 强制降至 marginal 档（最高 59 分）
   判断方法：逐一统计规范性表述，检查每个"应当"后是否有具体法条/程序/规则

5. 概念堆砌无操作化：论文使用≥3个专业术语作为核心框架，且≥2个无"本文所称XX是指..."的明确定义
   → 强制降至 marginal 档（最高 55 分）
   判断方法：列出所有核心术语，逐一检查是否有明确定义

6. 理论与制度脱节：引入跨学科理论但该理论核心术语在后文制度设计中出现<3次
   → 强制降至 good 档（最高 70 分）
   判断方法：搜索理论核心术语在后文中的出现频率

7. 宏观介绍非深度分析：论文只完成体系介绍，全文无任何具体问题的深入分析，无学者观点交锋
   → 强制降至 marginal 档（最高 59 分）

如果触发多个负面模式，取最低档。
将触发的负面模式记录在 score_rationale 中（如"触发口号式呼吁，强制降至marginal档"）。

【上限规则】："""

            if old_anchor in pt:
                pt = pt.replace(old_anchor, new_anchor)
                dim['prompt_template'] = pt
                print(f"  ✅ 分析框架：锚定表内嵌负面模式降档")
            else:
                print(f"  ⚠️ 分析框架：未找到【上限规则】标记")

        elif dim['key'] == 'conclusion_consensus':
            pt = dim['prompt_template']

            old_anchor = "【上限规则】："
            new_anchor = """【负面模式强制降档 - 优先于上限规则执行】：
在查表确定分档后，必须检查以下负面模式。如果触发，无论上面的分档结果如何，强制降档：

4. 生搬硬套机械框架：结论采用"立法-司法-执法-守法"或类似机械四分法，且每个方面无具体论证（只有空泛表述）
   → 强制降至 marginal 档（最高 55 分）
   判断方法：检查结论是否套用标准框架，每个方面是否有>50字的实质论证

5. 万能药式对策：对策建议≥3条且全部停留在"完善立法、加强监管、健全机制"层面（无具体法条/程序/规则）
   → 强制降至 marginal 档（最高 59 分）
   判断方法：逐条检查对策是否具体到法条、程序或裁判规则层面

6. 结论不足以支撑主张：提出新理论作为替代方案但未明确说明相对既有理论的优势
   → 强制降至 good 档（最高 70 分）

如果触发多个负面模式，取最低档。
将触发的负面模式记录在 score_rationale 中。

【上限规则】："""

            if old_anchor in pt:
                pt = pt.replace(old_anchor, new_anchor)
                dim['prompt_template'] = pt
                print(f"  ✅ 结论可接受性：锚定表内嵌负面模式降档")
            else:
                print(f"  ⚠️ 结论可接受性：未找到【上限规则】标记")

    # 3. 保存
    with open(target_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False, width=1000)

    print(f"\n✅ 已生成 {target_path}")


if __name__ == "__main__":
    apply_v2_50_3_rules()
