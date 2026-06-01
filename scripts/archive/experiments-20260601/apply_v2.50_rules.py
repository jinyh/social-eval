#!/usr/bin/env python3
"""
创建 v2.50 框架：扣分制负面模式检测

策略：
- 基于 v2.47（当前推荐版本）
- 不新增 ceiling_rules（v2.49 证明无效）
- 在 prompt_template 中注入明确的扣分指令
- 使用量化标准，减少 AI 的主观判断空间
"""
import yaml
from pathlib import Path

# 扣分制指令模板
PROBLEM_ORIGINALITY_PENALTY = """

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【负面模式扣分 - 必须执行】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

在确定最终分数前，必须逐项检查以下负面模式。如果满足条件，从当前分数中扣除对应分值。多个模式可叠加扣分。

□ 检查1：新概念包装旧问题（扣 15-25 分）
  触发条件：论文引入新概念/新术语作为核心创新点，但原文未明确说明新概念相对既有概念的理论进步
  量化标准：
  - 新概念未说明相对既有概念的任何优势 → 扣 25 分
  - 新概念只说"填补空白"但未说明解释力提升 → 扣 20 分
  - 新概念有部分说明但不充分 → 扣 15 分
  典型特征：用新词描述已有讨论（如用"权利遮蔽"描述"知情权无法实现"）

□ 检查2：宏观介绍非深度分析（扣 15-20 分）
  触发条件：论文完成了体系介绍但未触及现实问题，无不同学者观点的交锋
  量化标准：
  - 全文无任何学者观点交锋或理论分歧 → 扣 20 分
  - 有提及分歧但未展开讨论 → 扣 15 分
  典型特征：系统归纳既定立场（如"XX的法治建设"），主要是阐释而非争辩

□ 检查3：主题声明非研究问题（扣 20-30 分）
  触发条件：全文主要是阐释既定立场，无可争辩的法学争点
  量化标准：
  - 全文无任何问题句（"XX是否YY""如何ZZ"） → 扣 30 分
  - 有问题句但实质是政策倡导 → 扣 20 分
  典型特征：权威表述的系统归纳，主题重大但无争辩点

扣分后的分数不得低于 30 分。
将扣分情况记录在 score_rationale 中。
"""

ANALYTICAL_FRAMEWORK_PENALTY = """

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【负面模式扣分 - 必须执行】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

在确定最终分数前，必须逐项检查以下负面模式。如果满足条件，从当前分数中扣除对应分值。多个模式可叠加扣分。

□ 检查1：概念堆砌无操作化（扣 20-30 分）
  触发条件：论文使用≥3个专业术语/理论概念作为核心框架，但多数无定义或操作化
  量化标准：
  - 核心术语≥3个且≥2个无明确定义 → 扣 30 分
  - 核心术语≥3个且≥1个无明确定义 → 扣 20 分
  判断方法：逐一列出核心术语，检查每个是否有"本文所称XX是指..."的定义
  典型特征：大量使用"监管合作主义""穿透式监管""监管试验主义"等概念但未逐一界定

□ 检查2：口号式呼吁无具体展开（扣 15-25 分）
  触发条件：大量使用"应当""必须""需要"等规范性表述但无具体制度方案
  量化标准：
  - 规范性表述≥10处且无任何具体制度方案 → 扣 25 分
  - 规范性表述≥5处且无具体制度方案 → 扣 15 分
  判断方法：统计"应当""必须""需要完善""需要加强"等表述的数量
  典型特征：空谈义务、权利、责任，在论证深度上存在很大缺陷

□ 检查3：理论与制度脱节（扣 10-15 分）
  触发条件：引入跨学科理论但未真正用于后文分析
  量化标准：
  - 理论在后文分析中出现<2次 → 扣 15 分
  - 理论在后文分析中出现2-3次但无实质调用 → 扣 10 分
  判断方法：搜索理论核心术语在后文中的出现频率和调用方式
  典型特征：以XX理论作为分析视角，但后文制度设计未体现理论指导

□ 检查4：宏观介绍非深度分析（扣 15-20 分）
  触发条件：论文完成了体系构建的宏观介绍，但未触及该体系在现实中面临的具体问题
  量化标准：
  - 全文无任何具体问题的深入分析 → 扣 20 分
  - 有提及具体问题但未深入 → 扣 15 分
  典型特征：只是宏观介绍而无深度分析，无不同学者观点的交锋

扣分后的分数不得低于 30 分。
将扣分情况记录在 score_rationale 中。
"""

CONCLUSION_CONSENSUS_PENALTY = """

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【负面模式扣分 - 必须执行】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

在确定最终分数前，必须逐项检查以下负面模式。如果满足条件，从当前分数中扣除对应分值。多个模式可叠加扣分。

□ 检查1：生搬硬套机械框架（扣 15-25 分）
  触发条件：结论采用"立法-司法-执法-守法"四分法或类似机械框架，每个方面只有空泛表述
  量化标准：
  - 四分法且每个方面都无具体论证（<50字） → 扣 25 分
  - 四分法且≥2个方面无具体论证 → 扣 15 分
  判断方法：检查结论是否套用标准框架，每个方面是否有具体的制度方案或论证
  典型特征：从立法、司法、执法、守法四个方面开展论述，完全是生搬硬套

□ 检查2：结论不足以支撑主张（扣 10-15 分）
  触发条件：提出新理论/新框架作为既有理论的替代方案，但未说明相对优势
  量化标准：
  - 新理论未说明相对既有理论的任何优势 → 扣 15 分
  - 新理论有部分说明但不充分 → 扣 10 分
  判断方法：检查论文是否明确说明新理论能解决既有理论无法解决的问题
  典型特征：引入新框架但未给出令人满意的足以替代既有理论的效果

□ 检查3：万能药式对策（扣 10-20 分）
  触发条件：对策建议停留在"完善立法、加强监管、健全机制"等空泛表述
  量化标准：
  - 对策≥3条且全部为空泛表述（无具体法条/程序/规则） → 扣 20 分
  - 对策≥3条且≥2条为空泛表述 → 扣 10 分
  判断方法：检查每条对策是否具体到法条、程序或裁判规则层面
  典型特征：应完善XX制度、应加强YY保护、应健全ZZ机制

扣分后的分数不得低于 30 分。
将扣分情况记录在 score_rationale 中。
"""


def apply_v2_50_rules():
    """创建 v2.50 框架：扣分制"""

    source_path = Path("configs/frameworks/law-v2.47-20260511.yaml")
    target_path = Path("configs/frameworks/law-v2.50-20260514.yaml")

    with open(source_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # 1. 更新 metadata
    config['metadata']['name'] = "法学评价框架 v2.50（扣分制负面模式检测）"
    config['metadata']['version'] = "2.50.0"
    config['metadata']['created'] = "2026-05-14"
    config['metadata']['previous_version'] = "2.47.0"
    config['metadata']['source'] = "v2.47 + 扣分制负面模式检测"
    config['metadata']['changelog'] = """v2.50 变化（2026-05-14，扣分制负面模式检测）：
【目标】提升负样本识别率，使负样本平均分 < 75。

核心变化：
1. 放弃 v2.49 的 ceiling_rules 路线（验证证明无效，0% 触发率）
2. 在三个关键维度的 prompt_template 中注入【负面模式扣分】指令
3. 使用量化标准（如"≥3个术语且≥2个无定义 → 扣30分"），减少 AI 主观判断空间
4. 扣分制直接从当前分数中扣除，不依赖规则触发机制
5. 基于 v2.47（当前推荐版本），不引入仲裁机制

设计原理：
- v2.49 证明 ceiling_rules 无效：AI 倾向于宽松解释触发条件
- 扣分制更直接：不需要"触发"，只需要"检查并扣分"
- 量化标准减少主观性：如"≥10处规范性表述"比"大量使用"更明确

预期改进：
- 负样本平均分 < 75
- 正负样本差距 > 15 分
- 曹俊金 < 65 分（v2.48 为 55，v2.49 为 74.5）

定位：research / penalty-based detection。"""

    # 2. 在三个维度的 prompt_template 中注入扣分指令
    dimensions = config['dimensions']

    for dim in dimensions:
        if dim['key'] == 'problem_originality':
            # 在 prompt_template 末尾（JSON 输出之前）注入扣分指令
            pt = dim['prompt_template']
            # 在"第四步：确定分数"之前插入
            insert_marker = "第四步：确定分数"
            if insert_marker in pt:
                pt = pt.replace(
                    insert_marker,
                    PROBLEM_ORIGINALITY_PENALTY.strip() + "\n\n" + insert_marker
                )
            else:
                # 如果找不到标记，追加到末尾
                pt += "\n" + PROBLEM_ORIGINALITY_PENALTY
            dim['prompt_template'] = pt
            print(f"  ✅ 问题创新性：注入扣分指令")

        elif dim['key'] == 'analytical_framework':
            pt = dim['prompt_template']
            insert_marker = "第三步：确定分数"
            if insert_marker in pt:
                pt = pt.replace(
                    insert_marker,
                    ANALYTICAL_FRAMEWORK_PENALTY.strip() + "\n\n" + insert_marker
                )
            else:
                pt += "\n" + ANALYTICAL_FRAMEWORK_PENALTY
            dim['prompt_template'] = pt
            print(f"  ✅ 分析框架：注入扣分指令")

        elif dim['key'] == 'conclusion_consensus':
            pt = dim['prompt_template']
            insert_marker = "第三步：确定分数"
            if insert_marker in pt:
                pt = pt.replace(
                    insert_marker,
                    CONCLUSION_CONSENSUS_PENALTY.strip() + "\n\n" + insert_marker
                )
            else:
                pt += "\n" + CONCLUSION_CONSENSUS_PENALTY
            dim['prompt_template'] = pt
            print(f"  ✅ 结论可接受性：注入扣分指令")

    # 3. 保存
    with open(target_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False, width=1000)

    print(f"\n✅ 已生成 {target_path}")
    print(f"   - 基于 v2.47（推荐版本）")
    print(f"   - 问题创新性：3 个扣分检查项")
    print(f"   - 分析框架：4 个扣分检查项")
    print(f"   - 结论可接受性：3 个扣分检查项")
    print(f"   - 总计：10 个扣分检查项")


if __name__ == "__main__":
    apply_v2_50_rules()
