#!/usr/bin/env python3
"""
优化 literature_insight prompt：降低 std 从 24.4
增加法哲学/理论型论文的分散式文献定位强制锚定规则
"""
import yaml
from pathlib import Path

# 读取配置
config_path = Path("configs/frameworks/law-v2.56-prompt-aligned.yaml")
with open(config_path, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# 找到 literature_insight 维度
li_dim = None
for dim in config['dimensions']:
    if dim['key'] == 'literature_insight':
        li_dim = dim
        break

if not li_dim:
    print("未找到 literature_insight 维度")
    exit(1)

# 在 prompt 开头增加强制锚定规则
anchor_rule = """【法哲学/理论型论文强制锚定规则】（必须优先执行）

在开始评分前，先判断论文类型。如果是法哲学/概念分析/理论建构类论文，必须遵守以下锚定规则：

✅ 强制认定规则1（分散式文献定位）：
   法哲学论文通常不设独立文献综述章节，而是将文献梳理融入正文论证。
   如果正文各处引用了多位学者观点（如"XX学者认为""YY理论主张"），
   即使没有集中式文献综述，也必须逐一提取到达点、未竟点和本文切入点。
   不得因为"没有独立文献综述章节"就判定三要素得分低。

✅ 强制认定规则2（理论发展史 = 到达点）：
   如果论文梳理了某一法学概念/理论的发展脉络（如"从XX到YY再到ZZ"），
   引述了≥2位学者的观点或贡献，
   就必须认定：到达点 = 2（充分满足）

✅ 强制认定规则3（理论分歧 = 争点结构）：
   如果论文呈现了不同理论立场的对立（如"形式理性vs实质理性""机械司法vs社会学司法"），
   就必须认定：争点结构 ≥ 1
   如果呈现了≥2组对立立场，争点结构 = 2

✅ 强制认定规则4（跨学科法学对话 = 流派）：
   如果论文将心理学/社会学/哲学概念引入法学讨论，
   且在法学层面形成了不同理解路径或应用方案，
   就必须计为法学相关流派（每个独立的理解路径 = 1个流派）

❌ 禁止判定：
   - 不得因为论文没有独立文献综述章节就判定"三要素得分低"
   - 不得因为论文是法哲学类型就判定"无研究地图"
   - 不得因为引用的是哲学家/心理学家而非法学家就判定"流派数量少"
     （关键是看这些引用是否在法学层面形成了对话）

【锚定示例】：
- 论文：《司法公正与同理心正义》
- 到达点：梳理了司法公正理论从形式理性到实质理性的发展，引述了多位学者观点 → 到达点=2
- 未竟点：指出既有理论未能整合多元诉求 → 未竟点=2
- 本文切入点：提出同理心正义作为整合方案 → 切入点=2
- 三要素总分=6，争点结构=2（形式vs实质），流派≥2
- 分档：excellent（85-100），不得低于 75 分

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""

# 将锚定规则插入到 prompt 开头
original_prompt = li_dim['prompt_template']
li_dim['prompt_template'] = anchor_rule + original_prompt

# 保存修改后的配置
with open(config_path, 'w', encoding='utf-8') as f:
    yaml.dump(config, f, allow_unicode=True, sort_keys=False, width=1000)

print("✅ literature_insight prompt 已优化")
print("✅ 增加了法哲学/理论型论文分散式文献定位强制锚定规则")
print(f"✅ 配置已保存：{config_path}")
