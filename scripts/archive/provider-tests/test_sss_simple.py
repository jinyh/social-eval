#!/usr/bin/env python3
"""直接测试 SSS API - 模拟 codex 环境"""
import asyncio
import os
from pathlib import Path
from openai import AsyncOpenAI
from dotenv import load_dotenv

# 加载 .env 文件
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# 直接从环境变量读取
api_key = os.getenv("SSS_API_KEY")
base_url = os.getenv("SSS_BASE_URL", "https://codex1.sssaicode.com/api/v1")

print("=" * 60)
print("直接测试 SSS API")
print("=" * 60)
print(f"\nAPI Key: {api_key[:20] if api_key else 'None'}...")
print(f"Base URL: {base_url}")


async def test_simple():
    """最简单的测试"""
    print("\n测试 1: 最简单的调用")
    print("-" * 60)

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    try:
        response = await client.chat.completions.create(
            model="gpt-5.5",
            messages=[
                {"role": "user", "content": "Say 'Hello'"}
            ],
        )

        print(f"✅ 成功！")
        print(f"响应: {response.choices[0].message.content}")
        return True

    except Exception as e:
        print(f"❌ 失败: {e}")
        return False


async def test_with_all_params():
    """带所有常用参数的测试"""
    print("\n测试 2: 带完整参数")
    print("-" * 60)

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    try:
        response = await client.chat.completions.create(
            model="gpt-5.5",
            messages=[
                {"role": "user", "content": "Say 'Hello'"}
            ],
            temperature=0.7,
            max_tokens=100,
            top_p=1.0,
            frequency_penalty=0,
            presence_penalty=0,
        )

        print(f"✅ 成功！")
        print(f"响应: {response.choices[0].message.content}")
        return True

    except Exception as e:
        print(f"❌ 失败: {e}")
        return False


async def test_sync_version():
    """测试同步版本"""
    print("\n测试 3: 同步调用")
    print("-" * 60)

    from openai import OpenAI

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    try:
        response = client.chat.completions.create(
            model="gpt-5.5",
            messages=[
                {"role": "user", "content": "Say 'Hello'"}
            ],
        )

        print(f"✅ 成功！")
        print(f"响应: {response.choices[0].message.content}")
        return True

    except Exception as e:
        print(f"❌ 失败: {e}")
        return False


async def main():
    if not api_key:
        print("\n❌ 错误: 未找到 SSS_API_KEY 环境变量")
        print("请确保 .env 文件中配置了 SSS_API_KEY")
        return

    # 运行所有测试
    test1 = await test_simple()
    test2 = await test_with_all_params()

    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"简单调用: {'✅ 通过' if test1 else '❌ 失败'}")
    print(f"完整参数: {'✅ 通过' if test2 else '❌ 失败'}")

    if not (test1 or test2):
        print("\n尝试同步版本...")
        test3 = test_sync_version()
        print(f"同步调用: {'✅ 通过' if test3 else '❌ 失败'}")


if __name__ == "__main__":
    asyncio.run(main())
