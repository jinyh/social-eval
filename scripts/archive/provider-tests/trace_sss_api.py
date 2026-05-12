#!/usr/bin/env python3
"""追踪 OpenAI 客户端的实际请求 URL"""
import asyncio
import sys
from pathlib import Path
import logging

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import openai
from src.core.config import settings

# 启用详细日志
logging.basicConfig(level=logging.DEBUG)


async def trace_api_calls():
    """追踪 API 调用的实际 URL"""
    print("=" * 60)
    print("追踪 OpenAI 客户端的实际请求")
    print("=" * 60)

    print(f"\n配置:")
    print(f"  API Key: {settings.sss_api_key[:15]}...")
    print(f"  Base URL: {settings.sss_base_url}")

    client = openai.AsyncOpenAI(
        api_key=settings.sss_api_key,
        base_url=settings.sss_base_url,
        timeout=10.0,
    )

    # 测试 1: 获取模型列表（这个能成功）
    print("\n" + "=" * 60)
    print("测试 1: 获取模型列表（成功的调用）")
    print("=" * 60)

    try:
        print("\n调用 client.models.list()...")
        models = await client.models.list()
        print(f"✅ 成功获取 {len(models.data)} 个模型")
        print(f"   实际请求的 URL 应该是: {settings.sss_base_url}/models")
    except Exception as e:
        print(f"❌ 失败: {e}")

    # 测试 2: Chat Completions（这个失败）
    print("\n" + "=" * 60)
    print("测试 2: Chat Completions（失败的调用）")
    print("=" * 60)

    try:
        print("\n调用 client.chat.completions.create()...")
        response = await client.chat.completions.create(
            model="gpt-5.5",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=10,
        )
        print(f"✅ 成功: {response.choices[0].message.content}")
    except openai.NotFoundError as e:
        print(f"❌ 404 Not Found")
        print(f"   实际请求的 URL 应该是: {settings.sss_base_url}/chat/completions")
    except Exception as e:
        print(f"❌ 失败: {type(e).__name__}: {e}")

    # 测试 3: 尝试直接使用 httpx 调用 models 端点
    print("\n" + "=" * 60)
    print("测试 3: 直接 HTTP 调用 models 端点")
    print("=" * 60)

    import httpx

    async with httpx.AsyncClient() as http_client:
        models_url = f"{settings.sss_base_url}/models"
        print(f"\nGET {models_url}")

        try:
            response = await http_client.get(
                models_url,
                headers={"Authorization": f"Bearer {settings.sss_api_key}"},
            )
            print(f"  状态码: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"  ✅ 成功，返回 {len(data.get('data', []))} 个模型")
        except Exception as e:
            print(f"  ❌ 错误: {e}")

    # 测试 4: 尝试不同的 chat 端点路径
    print("\n" + "=" * 60)
    print("测试 4: 尝试不同的 chat 端点路径")
    print("=" * 60)

    base = settings.sss_base_url.rstrip('/')
    chat_variants = [
        f"{base}/chat/completions",
        f"{base}/chat",
        f"{base}/completions",
        f"{base}/generate",
        f"{base}/inference",
    ]

    async with httpx.AsyncClient() as http_client:
        for url in chat_variants:
            print(f"\nPOST {url}")
            try:
                response = await http_client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {settings.sss_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "gpt-5.5",
                        "messages": [{"role": "user", "content": "Hello"}],
                        "max_tokens": 10,
                    },
                    timeout=10.0,
                )
                print(f"  状态码: {response.status_code}")
                if response.status_code == 200:
                    print(f"  ✅ 成功！")
                    print(f"  响应: {response.text[:200]}")
                    return url
                else:
                    print(f"  响应: {response.text[:100]}")
            except Exception as e:
                print(f"  ❌ 错误: {e}")

    return None


async def main():
    print("\n🔍 追踪 SSS Provider API 调用\n")

    working_url = await trace_api_calls()

    print("\n" + "=" * 60)
    print("总结")
    print("=" * 60)

    if working_url:
        print(f"\n✅ 找到可用的端点: {working_url}")
    else:
        print("\n❌ 未找到可用的 chat 端点")
        print("\n观察:")
        print("  - /models 端点可以访问")
        print("  - /chat/completions 端点返回 404")
        print("  - 这可能意味着:")
        print("    1. SSS 使用了非标准的 API 路径")
        print("    2. 需要特殊的请求头或参数")
        print("    3. Chat 功能可能需要不同的调用方式")


if __name__ == "__main__":
    asyncio.run(main())
