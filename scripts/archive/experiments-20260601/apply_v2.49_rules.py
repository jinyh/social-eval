#!/usr/bin/env python3
"""
应用 v2.49 负面模式检测规则到框架配置文件
"""
import yaml
from pathlib import Path

def apply_v2_49_rules():
    """应用 v2.49 的 9 个负面模式检测规则"""

    # 读取 v2.48-optimized 作为基础
    source_path = Path("configs/frameworks/law-v2.48-optimized.yaml")
    target_path = Path("configs/frameworks/law-v2.49-20260514.yaml")

    with open(source_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # 1. 更新 metadata
    config['metadata']['name'] = "法学评价框架 v2.49（强化致命缺陷检测）"
    config['metadata']['version'] = "2.49.0"
    config['metadata']['created'] = "2026-05-14"
    config['metadata']['previous_version'] = "2.48.1"
    config['metadata']['source'] = "v2.48-optimized + 9 个负面模式检测规则"
    config['metadata']['changelog'] = """v2.49 变化（2026-05-14，强化致命缺陷检测）：
【目标】将专家意见中的批评模式转化为 prompt 中的强制检测规则，提升负样本识别率。

核心变化：
1. 问题创新性维度：增加 new_term_old_problem 规则，强化 weak_problem_formulation 和 no_justiciable_question。
2. 分析框架维度：增加 slogan_advocacy、concept_stacking、theory_practice_gap 规则，强化 no_operational_framework。
3. 结论可接受性维度：增加 mechanical_application 和 insufficient_support 规则。
4. 在三个维度的 prompt_template 中增加【负面模式强制检测】环节。
5. 保留 v2.48-optimized 的仲裁机制和聚合策略。

背景（v2.48-optimized 测试结果）：
- 负样本平均分 85.2（目标 < 75）
- 正负样本差距 2.7（目标 > 15）
- 仲裁机制和换模型都无效

根本原因：AI 看形式要素，专家看论证深度。负样本具备形式要素但缺乏深度。

预期改进：
- 负样本平均分 < 75
- 正负样本差距 > 15 分
- 负样本致命缺陷识别率 > 70%

定位：research / negative pattern detection。需用 3 篇负样本快速验证，再用 10 篇补充负样本批量测试。"""

    # 2. 找到 dimensions 列表
    dimensions = config['dimensions']

    # 3. 为每个维度添加新规则
    for dim in dimensions:
        if dim['key'] == 'problem_originality':
            # 添加 new_term_old_problem 规则
            new_rule = {
                'rule_id': 'problem_originality.new_term_old_problem',
                'trigger': '用新术语重新描述已有讨论，但未展示新概念相对旧概念的进步或解释力提升',
                'score_ceiling': 65,
                'priority': 2,
                'severity': 'major',
                'detection_method': '''检查论文是否引入新概念/新术语作为核心创新点；
若是，检查原文是否说明：
(1) 新概念相对既有概念的理论进步在哪里
(2) 新概念是否改变了问题的解释路径或规范判断
(3) 新概念是否只是既有讨论的重新包装
若只有新术语但无实质推进，触发此规则''',
                'examples': [
                    "提出'权利遮蔽'概念，但实质是用新词描述'知情权/申辩权无法实现'这一已有讨论",
                    "引入'XX理论'作为标题，但正文仍是既有观点的复述"
                ],
                'anti_examples': [
                    "新概念明确说明相对既有概念的理论进步（如解释力更强、适用范围更广）",
                    "新概念改变了问题的分析路径或规范判断"
                ]
            }
            dim['ceiling_rules'].append(new_rule)

            # 强化现有规则
            for rule in dim['ceiling_rules']:
                if rule['rule_id'] == 'problem_originality.weak_problem_formulation':
                    rule['detection_method'] = '''检查问题陈述是否包含'为什么这是问题'的论证；若只有'尚未研究'或纯宏观叙事而无具体争点，则触发。
【新增】检查是否属于"宏观介绍非深度分析"：
- 论文完成了体系介绍但未触及现实问题
- 无不同学者观点的交锋
- 只是系统归纳既定立场而非提出可争辩的争点'''
                elif rule['rule_id'] == 'problem_originality.no_justiciable_question':
                    rule['detection_method'] = '''检查论文是否包含：(1)明确的问题句或争点；(2)与法律规范、法律制度或法律理论相关的讨论。若只有政策背景描述或纯事实陈述，无任何法学层面的争辩点，则触发。
【新增】检查是否属于"主题声明非研究问题"：
- 全文主要是阐释既定立场（如"爱国主义的法治建设"）
- 无可争辩的法学争点，只是权威表述的系统归纳
- 只要全文主要是在阐释既定立场而非提出可争辩的法学争点，就不得因为主题重大而给高分'''

        elif dim['key'] == 'analytical_framework':
            # 添加三个新规则
            new_rules = [
                {
                    'rule_id': 'analytical_framework.slogan_advocacy',
                    'trigger': '空谈义务、权利、责任，无具体制度方案或裁判规则；或大量使用"应当""必须"等规范性表述但无操作化路径',
                    'score_ceiling': 60,
                    'priority': 2,
                    'severity': 'major',
                    'detection_method': '''检查论文是否大量使用规范性表述（"应当""必须""需要"）；
若是，检查是否提供：
(1) 具体的制度设计方案
(2) 可操作的裁判规则或程序衔接
(3) 法学层面的操作化路径
若只有口号式呼吁而无具体展开，触发此规则''',
                    'examples': [
                        "应当完善XX制度、加强YY保护，但无具体制度方案",
                        "空谈义务、权利、责任，在论证深度上存在很大缺陷"
                    ],
                    'anti_examples': [
                        "提出具体的裁判规则：当XX情形时，应采用YY解释路径",
                        "给出制度设计方案：建议在ZZ条件下设立AA机制"
                    ]
                },
                {
                    'rule_id': 'analytical_framework.concept_stacking',
                    'trigger': '大量使用术语（如"监管合作主义""穿透式监管""监管试验主义"）但无定义或操作化',
                    'score_ceiling': 55,
                    'priority': 1,
                    'severity': 'critical',
                    'detection_method': '''检查论文是否使用≥3个专业术语/理论概念作为核心框架；
若是，检查每个核心术语是否：
(1) 有明确的法学界定或定义
(2) 有分析步骤或操作化路径
(3) 在后文中被真正调用（≥2次）
若核心术语堆砌但无定义或操作化，触发此规则''',
                    'examples': [
                        "大量使用'监管合作主义''穿透式监管''监管试验主义'等概念进行堆砌，并未对这些概念作出详细解释",
                        "引入多个理论概念但只在绪论出现，后文未真正调用"
                    ],
                    'anti_examples': [
                        "每个核心概念都有法学界定，并在后文分析中被反复调用"
                    ]
                },
                {
                    'rule_id': 'analytical_framework.theory_practice_gap',
                    'trigger': '引入理论框架但未真正用于分析，或理论与后文制度设计脱节',
                    'score_ceiling': 70,
                    'priority': 3,
                    'severity': 'minor',
                    'detection_method': '''检查论文是否引入跨学科理论（如社会技术系统理论、经济学理论）；
若是，检查：
(1) 理论是否在后文分析中被真正调用
(2) 理论与制度设计之间的连接是否清晰
(3) 理论是否只是装饰性引用
若理论与制度设计脱节，触发此规则''',
                    'examples': [
                        "以社会技术系统理论作为分析视角，但该理论与后文算法审计制度之间的连接并不算强",
                        "引入XX理论但只在绪论出现，后文制度设计未体现理论指导"
                    ],
                    'anti_examples': [
                        "理论在后文每个制度设计环节都被明确调用",
                        "理论与制度设计之间有清晰的推导路径"
                    ]
                }
            ]
            dim['ceiling_rules'].extend(new_rules)

            # 强化现有规则
            for rule in dim['ceiling_rules']:
                if rule['rule_id'] == 'analytical_framework.no_operational_framework':
                    rule['detection_method'] = '''同时检查三项：(1)核心术语是否有定义；(2)是否有可循的分析步骤；(3)是否有法学转化（裁判规则/司法程序/法律适用步骤）。三项均不满足才触发。若框架来自跨学科但已转化为法学操作步骤，则不触发。
【新增】检查是否属于"宏观介绍非深度分析"：
- 论文完成了体系构建的宏观介绍
- 但未触及该体系在现实中面临的具体问题
- 无不同学者观点在此的交锋
若只是宏观介绍而无深度分析，触发此规则'''

        elif dim['key'] == 'conclusion_consensus':
            # 添加两个新规则
            new_rules = [
                {
                    'rule_id': 'conclusion_consensus.mechanical_application',
                    'trigger': '结论从立法、司法、执法、守法四个方面生搬硬套，无法令人接受',
                    'score_ceiling': 60,
                    'priority': 2,
                    'severity': 'major',
                    'detection_method': '''检查结论是否采用"立法-司法-执法-守法"四分法或类似机械框架；
若是，检查：
(1) 每个方面是否有具体的制度方案或论证
(2) 四分法是否与正文论证有机衔接
(3) 是否只是套用框架而无实质内容
若生搬硬套无法令人接受，触发此规则''',
                    'examples': [
                        "在结论上试图建立起一套XX实施的法律体系，从立法、司法、执法、守法四个方面开展论述，完全是生搬硬套",
                        "套用标准框架但每个方面都只有空泛表述"
                    ],
                    'anti_examples': [
                        "四分法与正文论证有机衔接，每个方面都有具体论证"
                    ]
                },
                {
                    'rule_id': 'conclusion_consensus.insufficient_support',
                    'trigger': '引入新理论/新框架但未给出令人满意的足以替代既有理论的效果',
                    'score_ceiling': 70,
                    'priority': 3,
                    'severity': 'minor',
                    'detection_method': '''检查论文是否提出新理论/新框架作为既有理论的替代方案；
若是，检查：
(1) 新理论是否明确说明相对既有理论的优势
(2) 新理论是否能解决既有理论无法解决的问题
(3) 新理论是否足以形成成熟的权利义务配置方案
若新理论不足以替代既有理论，触发此规则''',
                    'examples': [
                        "虽然引入身份分层理论来试图解决人格权商业化利用上既有理论所面临的困境，但是并未对此给出一个令人满意的足以替代既有理论的效果",
                        "提出新框架但未说明相对既有方案的优势"
                    ],
                    'anti_examples': [
                        "新理论明确说明相对既有理论的优势，并能解决既有理论的核心困境"
                    ]
                }
            ]
            dim['ceiling_rules'].extend(new_rules)

    # 4. 保存到目标文件
    with open(target_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False, width=1000)

    print(f"✅ 已生成 {target_path}")
    print(f"   - 更新了 metadata")
    print(f"   - 问题创新性：新增 1 个规则，强化 2 个规则")
    print(f"   - 分析框架：新增 3 个规则，强化 1 个规则")
    print(f"   - 结论可接受性：新增 2 个规则")
    print(f"   - 总计：新增 6 个规则，强化 3 个规则")

if __name__ == "__main__":
    apply_v2_49_rules()
