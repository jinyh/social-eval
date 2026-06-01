#!/usr/bin/env python3
"""
优化 logical_coherence prompt：降低 std 从 20.3
增加法哲学/理论型论文的推理链和反驳处理强制锚定规则
"""
import yaml
from pathlib import Path

# 读取配置
config_path = Path("configs/frameworks/law-v2.56-prompt-aligned.yaml")
with open(config_path, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# 找到 logical_coherence 维度
lc_dim = None
for dim in config['dimensions']:
    if dim['key'] == 'logical_coherence':
        lc_dim = dim
        break

if not lc_dim:
    print("未找到 logical_coherence 维度")
    exit(1)

# 在 prompt 开头增加强制锚定规则
anchor_rule = """【法哲学/理论型论文强制锚定规则】（必须优先执行）

在开始评分前，先判断论文类型。如果是法哲学/概念分析/理论建构类论文，必须遵守以下锚定规则：

✅ 强制认定规则1（理论推演 = 推理链）：
   法哲学论文的推理链形式与制度论文不同。以下形式均构成有效推理链：
   - 概念界定 → 概念操作化 → 理论应用 → 结论
   - 问题提出 → 理论回顾 → 理论重构 → 新框架提出
   - 现象描述 → 理论解释 → 规范推导 → 制度启示
   只要论文的理论推演有明确的逻辑递进关系（后一步依赖前一步），就必须认定推理链完整性 ≥ 3

✅ 强制认定规则2（隐含分歧回应 = 反驳处理）：
   法哲学论文的反驳处理形式与制度论文不同。以下形式均构成有效反驳处理：
   - 呈现不同理论立场并说明为何选择某一路径（隐含分歧回应）
   - 讨论理论的适用边界或局限条件（承认局限）
   - 回应可能的理论质疑（如"有人可能认为XX，但本文认为YY因为ZZ"）
   只要论文有上述任一形式的反驳处理，就必须认定反驳处理度 ≥ 1

✅ 强制认定规则3（理论论证的"充分支撑"标准）：
   对法哲学论文，"充分支撑"不要求实证数据或判例支持。
   以下均构成充分支撑：
   - 概念分析和逻辑推演
   - 思想实验或假设论证
   - 理论传统内的学术对话
   - 跨学科理论的类比推理
   不得因为法哲学论文缺少实证数据或判例就判定"结论无法推出"。

❌ 禁止判定：
   - 不得因为论文是理论推演而非实证研究就判定"推理链不完整"
   - 不得因为论文没有处理所有可能的反对意见就判定"反驳处理不足"
   - 不得因为论文的结论是理论性的（而非制度性的）就判定"结论无法推出"
   - 不得将"理论推演的跳跃性"等同于"关键跳步"——理论论文允许合理的抽象跳跃

【锚定示例】：
- 论文：《司法公正与同理心正义》
- 推理链：问题提出（司法公正困境）→ 理论回顾（形式理性vs实质理性）→ 概念重构（同理心正义）→ 操作化（四步运作机理）→ 应用论证
- 判定：推理链完整性 ≥ 3（有递进关系、有依赖度、结论可推出）
- 反驳处理：呈现了形式理性vs实质理性的分歧并说明选择理由 → 反驳处理度 ≥ 2
- 分档：excellent 或 good（80-100 或 60-79），不得低于 60 分

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""

# 将锚定规则插入到 prompt 开头
original_prompt = lc_dim['prompt_template']
lc_dim['prompt_template'] = anchor_rule + original_prompt

# 保存修改后的配置
with open(config_path, 'w', encoding='utf-8') as f:
    yaml.dump(config, f, allow_unicode=True, sort_keys=False, width=1000)

print("✅ logical_coherence prompt 已优化")
print("✅ 增加了法哲学/理论型论文推理链和反驳处理强制锚定规则")
print(f"✅ 配置已保存：{config_path}")
