#!/usr/bin/env python3
"""调试 Round 2 错误"""

import json
from pathlib import Path

# 读取第一篇论文的 Round 1 结果
round1_file = Path("results/phase2-1849-papers/batch-1/round1/paper-1.json")

with open(round1_file, 'r', encoding='utf-8') as f:
    round1_result = json.load(f)

# 检查 dimensions 结构
dimensions_data = round1_result.get("dimensions", {})

print("=== Dimensions keys ===")
print(list(dimensions_data.keys()))
print()

# 检查第一个维度的结构
first_dim_key = list(dimensions_data.keys())[0]
first_dim_data = dimensions_data[first_dim_key]

print(f"=== {first_dim_key} structure ===")
print(f"Keys: {list(first_dim_data.keys())}")
print()

# 检查 raw_outputs 结构
raw_outputs = first_dim_data.get("raw_outputs", {})
print(f"=== raw_outputs type: {type(raw_outputs)} ===")
print(f"Keys: {list(raw_outputs.keys())}")
print()

# 检查第一个模型的输出
first_model = list(raw_outputs.keys())[0]
first_output = raw_outputs[first_model]

print(f"=== {first_model} output type: {type(first_output)} ===")
if isinstance(first_output, dict):
    print(f"Keys: {list(first_output.keys())}")
    print(f"Score: {first_output.get('score')}")
elif isinstance(first_output, list):
    print(f"Length: {len(first_output)}")
    print(f"First element type: {type(first_output[0]) if first_output else 'empty'}")
else:
    print(f"Unexpected type: {type(first_output)}")
