#!/usr/bin/env python3
"""
优化 forward_extension prompt：降低 std 从 18.9
增加法哲学/理论型论文的延展路径强制锚定规则
"""
import yaml
from pathlib import Path

# 读取配置
config_path = Path("configs/frameworks/law-v2.56-prompt-aligned.yaml")
with open(config_path, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# 找到 forward_extension 维度
fe_dim = None
for dim in config['dimensions']:
    if dim['key'] == 'forward_extension':
        fe_dim = dim
        break

if not fe_dim:
    print("未找到 forward_extension 维度")
    exit(1)

# 在 prompt 开头增加强制锚定规则
anchor_rule = """【法哲学/理论型论文强制锚定规则】（必须优先执行）

在开始评分前，先判断论文类型。如果是法哲学/概念分析/理论建构类论文，必须遵守以下锚定规则：

✅ 强制认定规则1（理论深化方向 = 有效延展）：
   法哲学论文的延展形式与制度论文不同。以下形式均构成有效延展路径：
   - 指出理论框架可进一步深化的方向（如"本框架可扩展至XX领域"）
   - 提出概念修正或完善的路径（如"XX概念的边界条件有待进一步厘清"）
   - 指明理论与制度衔接的可能方向（如"本理论可为XX制度改革提供正当化基础"）
   - 承认理论局限并指出后续研究应关注的问题
   - 指出反对者可从何处进入争论（开放争辩入口）
   只要论文有上述任一形式的延展，就必须认定存在真实延展路径，分数 ≥ 60

✅ 强制认定规则2（理论论文不要求实证研究设计）：
   不得因为法哲学论文没有提出"实证研究设计""数据收集方案"或"具体制度改革路线图"
   就判定"延展路径不清晰"或"只有口号式展望"。
   理论论文的延展本质是理论层面的，不是实务层面的。

✅ 强制认定规则3（隐含延展 = 有效延展）：
   如果论文在正文论证中隐含了延展方向（如讨论了理论的适用边界、承认了某些问题未解决），
   即使没有在结尾专门设置"未来研究"章节，也必须认定存在延展路径。
   不得因为论文没有明确的"展望"或"未来研究"段落就判定延展不足。

❌ 禁止判定：
   - 不得因为论文是法哲学类型就判定"延展路径不具体"
   - 不得因为论文没有实证研究设计就判定"延展不清晰"
   - 不得因为论文的延展是理论层面的（而非制度层面的）就给低分
   - 不得将"理论可进一步深化"判定为"口号式展望"——这是理论论文的正常延展形式

【锚定示例】：
- 论文：《司法公正与同理心正义》
- 延展路径：同理心正义框架可扩展至其他裁判领域；四步运作机理的边界条件有待厘清；与其他正义理论的对话空间
- 判定：存在真实延展路径（理论深化方向+概念修正路径+争辩入口）
- 分档：good 或 excellent（60-100），不得低于 55 分

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""

# 将锚定规则插入到 prompt 开头
original_prompt = fe_dim['prompt_template']
fe_dim['prompt_template'] = anchor_rule + original_prompt

# 保存修改后的配置
with open(config_path, 'w', encoding='utf-8') as f:
    yaml.dump(config, f, allow_unicode=True, sort_keys=False, width=1000)

print("✅ forward_extension prompt 已优化")
print("✅ 增加了法哲学/理论型论文延展路径强制锚定规则")
print(f"✅ 配置已保存：{config_path}")
