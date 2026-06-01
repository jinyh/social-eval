#!/usr/bin/env python3
"""
优化 conclusion_consensus prompt：降低 std 从 26.0
增加法哲学/理论型论文的共同体对话和制度可接受性强制锚定规则
"""
import yaml
from pathlib import Path

# 读取配置
config_path = Path("configs/frameworks/law-v2.56-prompt-aligned.yaml")
with open(config_path, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# 找到 conclusion_consensus 维度
cc_dim = None
for dim in config['dimensions']:
    if dim['key'] == 'conclusion_consensus':
        cc_dim = dim
        break

if not cc_dim:
    print("未找到 conclusion_consensus 维度")
    exit(1)

# 在 prompt 开头增加强制锚定规则
anchor_rule = """【法哲学/理论型论文强制锚定规则】（必须优先执行）

在开始评分前，先判断论文类型。如果是法哲学/概念分析/理论建构类论文，必须遵守以下锚定规则：

✅ 强制认定规则1（理论贡献 = 共同体对话）：
   法哲学论文的结论形式与制度论文不同。以下形式均构成有效的共同体对话：
   - 提出新的理论框架并说明其与既有理论的关系（如"本文提出的XX框架回应了YY争论"）
   - 重构既有概念并说明重构的理论意义（如"将XX重新理解为YY，可以解决ZZ困境"）
   - 在理论层面回应了法学共同体的核心争论（如形式法治vs实质法治）
   只要论文结论能被法学共同体定位和回应，就必须认定共同体对话度 ≥ 2

✅ 强制认定规则2（理论兼容性 = 制度可接受性）：
   对法哲学论文，"制度可接受性"不要求具体制度方案。以下形式均满足：
   - 结论与现行法秩序的基本逻辑不矛盾（兼容性）
   - 结论在原则层面回应了制度约束（如"本理论框架不否定现行法治原则"）
   - 结论指出了理论与制度的衔接方向（即使未给出具体方案）
   不得因为法哲学论文没有提出具体制度改革方案就判定"制度可接受性低"。
   只要结论不与现行法秩序根本矛盾，就必须认定制度可接受度 ≥ 2

✅ 强制认定规则3（理论论文的"反对者可定位"标准）：
   如果论文的结论是在回应法学基础理论争论（如正义论、法治论、权利论），
   且结论有明确的理论立场（而非模糊的折中），
   就必须认定：反对者可定位 = 满足（因为持不同理论立场的学者可以回应）

❌ 禁止判定：
   - 不得因为论文是法哲学类型就判定"结论自说自话"
   - 不得因为论文没有具体制度方案就判定"无制度锚定"
   - 不得因为论文结论是理论性的就判定"共同体无法回应"
   - 不得因为论文引入跨学科概念就判定"不在法学共同体语境内"

【锚定示例】：
- 论文：《司法公正与同理心正义》
- 结论：同理心正义可作为整合多元诉求的裁判正当性基础
- 共同体对话：回应了形式理性vs实质理性的核心争论 → 共同体对话度=3
- 制度可接受性：不否定现行法治原则，提供了裁判正当化的新路径 → 制度可接受度=2
- 分档：good 或 excellent（60-100），不得低于 60 分

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""

# 将锚定规则插入到 prompt 开头
original_prompt = cc_dim['prompt_template']
cc_dim['prompt_template'] = anchor_rule + original_prompt

# 保存修改后的配置
with open(config_path, 'w', encoding='utf-8') as f:
    yaml.dump(config, f, allow_unicode=True, sort_keys=False, width=1000)

print("✅ conclusion_consensus prompt 已优化")
print("✅ 增加了法哲学/理论型论文共同体对话强制锚定规则")
print(f"✅ 配置已保存：{config_path}")
