#!/usr/bin/env python3
"""验证 SSS 同步调用确实可以工作"""
import os
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

# 加载 .env 文件
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# 直接从环境变量读取
api_key = os.getenv("SSS_API_KEY")
base_url = os.getenv("SSS_BASE_URL", "https://codex1.sssaicode.com/api/v1")

print("=" * 60)
print("验证 SSS 同步调用")
print("=" * 60)
print(f"\nAPI Key: {api_key[:20] if api_key else 'None'}...")
print(f"Base URL: {base_url}")

if not api_key:
    print("\n❌ 错误: 未找到 SSS_API_KEY")
    exit(1)

print("\n测试同步调用...")
print("-" * 60)

try:
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    response = client.chat.completions.create(
        model="gpt-5.5",
        messages=[
            {"role": "user", "content": "请用中文回答：什么是人工智能？限制在50字以内。"}
        ],
        temperature=0.3,
        max_tokens=100,
    )

    print(f"✅ 成功！")
    print(f"\n响应内容:")
    print(f"{response.choices[0].message.content}")
    print(f"\n模型: {response.model}")
    print(f"Token 使用: {response.usage.total_tokens if response.usage else 'N/A'}")

except Exception as e:
    print(f"❌ 失败: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n" + "=" * 60)
print("✅ SSS 同步调用验证成功！")
print("=" * 60)
