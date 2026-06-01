#!/usr/bin/env python3
"""
优化 analytical_framework prompt：增加理论型论文强制锚定规则
"""
import yaml
from pathlib import Path

# 读取配置
config_path = Path("configs/frameworks/law-v2.56-prompt-aligned.yaml")
with open(config_path, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# 找到 analytical_framework 维度
af_dim = None
for dim in config['dimensions']:
    if dim['key'] == 'analytical_framework':
        af_dim = dim
        break

if not af_dim:
    print("未找到 analytical_framework 维度")
    exit(1)

# 在 prompt 开头增加强制锚定规则
anchor_rule = """【理论型论文强制锚定规则】（必须优先执行）

在开始评分前，先判断论文类型。如果是理论型论文（法哲学/概念分析类），必须遵守以下锚定规则：

✅ 强制认定规则1：如果论文提出了操作化步骤（如"四步运作机理""三阶段分析框架"等），
   即使这些步骤来自跨学科概念（心理学、社会学等），
   只要步骤本身可操作、可重复适用，
   就必须认定：框架可操作性 ≥ 3（满足标准1概念界定 + 标准3分析步骤 + 标准4后文调用）

✅ 强制认定规则2：如果论文提供了概念的操作化定义和适用边界（如"XX适用于YY情境，不适用于ZZ"），
   就必须认定：法学转化度 ≥ 2（满足标准1跨学科转化 + 标准2操作指引）

❌ 禁止判定：不得因为概念来自心理学/社会学/经济学就判定"理论贴标签"或触发 no_operational_framework 上限。
   只有当概念完全无定义、无操作步骤、无法学转化时，才能触发上限规则。

【锚定示例】：
- 论文：《司法公正与同理心正义》
- 框架：同理心正义的四步运作机理（移情联想→位阶排序→反思权衡→理由优化）
- 判定：框架可操作性 ≥ 3（有步骤、可操作、后文使用），法学转化度 ≥ 2（有操作化定义、有适用指引）
- 分档：excellent 或 good（80-100 或 60-79），不得低于 60 分

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""

# 将锚定规则插入到 prompt 开头
original_prompt = af_dim['prompt_template']
af_dim['prompt_template'] = anchor_rule + original_prompt

# 保存修改后的配置
with open(config_path, 'w', encoding='utf-8') as f:
    yaml.dump(config, f, allow_unicode=True, sort_keys=False, width=1000)

print("✅ analytical_framework prompt 已优化")
print("✅ 增加了理论型论文强制锚定规则")
print(f"✅ 配置已保存：{config_path}")
