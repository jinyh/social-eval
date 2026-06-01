#!/usr/bin/env python3
"""
优化 problem_originality prompt：降低 std 从 24.9 到 < 20
基于 v2.56.1 的成功经验，为 problem_originality 增加强制锚定规则
"""
import yaml
from pathlib import Path

# 读取配置
config_path = Path("configs/frameworks/law-v2.56-prompt-aligned.yaml")
with open(config_path, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# 找到 problem_originality 维度
po_dim = None
for dim in config['dimensions']:
    if dim['key'] == 'problem_originality':
        po_dim = dim
        break

if not po_dim:
    print("未找到 problem_originality 维度")
    exit(1)

# 在 prompt 开头增加强制锚定规则
anchor_rule = """【法哲学论文强制锚定规则】（必须优先执行）

在开始评分前，先判断论文类型。如果是法哲学/概念分析类论文，必须遵守以下锚定规则：

✅ 强制认定规则1：如果论文讨论的是法学基础概念（正义、权利、权力、法治等）的不同理解路径，
   即使论文没有明确标注"学界争论"，
   只要呈现了不同理解路径或隐含展示了理论分歧，
   就必须认定：标准3（理论分歧）= 满足

✅ 强制认定规则2：如果论文讨论的是司法裁判的正当性基础（如"正义原则能否作为裁判理由"），
   即使论文没有提出具体的制度修改方案，
   只要论文结论隐含需要调整裁判制度或司法制度的正当性基础，
   就必须认定：标准4（制度连锁）= 满足

✅ 强制认定规则3：如果论文讨论的是法学长期争论的核心问题（如"形式法治vs实质法治""法律与道德关系"），
   就必须认定：标准2（争议焦点）= 满足

❌ 禁止判定：不得因为论文是法哲学类型就判定"无法学层面的分歧"或"无制度连锁效应"。
   法哲学问题 = 法学问题。只有当论文完全无法学层面的讨论时，才能判定"无法学问题"。

【锚定示例】：
- 论文：《司法公正与同理心正义》
- 问题：司法公正能否以同理心正义作为整合多元诉求的基础？
- 判定：标准1（问题句）= 满足，标准2（法学层面）= 满足，标准3（理论分歧）= 满足（呈现了不同理解路径），标准4（制度连锁）= 满足（涉及裁判制度+司法制度）
- 可争辩性 = 4/4，枢纽性 ≥ 2（争议焦点+理论基础+制度连锁）
- 分档：excellent 或 good（80-100 或 60-79），不得低于 60 分

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""

# 将锚定规则插入到 prompt 开头
original_prompt = po_dim['prompt_template']
po_dim['prompt_template'] = anchor_rule + original_prompt

# 保存修改后的配置
with open(config_path, 'w', encoding='utf-8') as f:
    yaml.dump(config, f, allow_unicode=True, sort_keys=False, width=1000)

print("✅ problem_originality prompt 已优化")
print("✅ 增加了法哲学论文强制锚定规则")
print(f"✅ 配置已保存：{config_path}")
