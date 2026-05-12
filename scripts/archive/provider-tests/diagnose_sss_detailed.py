#!/usr/bin/env python3
"""详细诊断 SSS Provider 的 API 端点路径"""
import asyncio
import sys
from pathlib import Path
import httpx

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import openai
from src.core.config import settings


async def test_chat_endpoint_variants():
    """测试不同的 chat completions 端点路径"""
    print("=" * 60)
    print("测试 Chat Completions 端点路径")
    print("=" * 60)

    base_url = settings.sss_base_url.rstrip('/')

    # 可能的端点路径
    endpoint_variants = [
        f"{base_url}/chat/completions",
        f"{base_url}/v1/chat/completions",
        f"{base_url}/api/v1/chat/completions",
        f"{base_url}/openai/v1/chat/completions",
        f"{base_url}/completions",
        f"{base_url}/v1/completions",
    ]

    print(f"\n当前 Base URL: {base_url}")
    print(f"API Key: {settings.sss_api_key[:15]}...\n")

    # 测试每个端点
    async with httpx.AsyncClient(timeout=10.0) as client:
        for i, endpoint in enumerate(endpoint_variants, 1):
            print(f"[{i}/{len(endpoint_variants)}] 测试: {endpoint}")

            try:
                response = await client.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {settings.sss_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "gpt-5.5",
                        "messages": [{"role": "user", "content": "Hello"}],
                        "max_tokens": 10,
                    },
                )

                print(f"  状态码: {response.status_code}")

                if response.status_code == 200:
                    data = response.json()
                    print(f"  ✅ 成功！响应: {data}")
                    return endpoint
                elif response.status_code == 404:
                    print(f"  ❌ 404 Not Found")
                elif response.status_code == 401:
                    print(f"  ⚠️  401 认证错误（但端点可能存在）")
                else:
                    print(f"  ⚠️  响应: {response.text[:200]}")

            except Exception as e:
                print(f"  ❌ 错误: {e}")

            print()

    return None


async def test_with_openai_client():
    """使用 OpenAI 客户端测试不同的 base_url 配置"""
    print("=" * 60)
    print("使用 OpenAI 客户端测试")
    print("=" * 60)

    # 尝试不带 /v1 后缀的 base_url
    base_url_no_v1 = settings.sss_base_url.replace('/api/v1', '').replace('/v1', '')

    print(f"\n测试 Base URL: {base_url_no_v1}")
    print("（OpenAI 客户端会自动添加 /v1/chat/completions）\n")

    try:
        client = openai.AsyncOpenAI(
            api_key=settings.sss_api_key,
            base_url=base_url_no_v1,
            timeout=10.0,
        )

        response = await client.chat.completions.create(
            model="gpt-5.5",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=10,
        )

        print(f"✅ 成功！响应: {response.choices[0].message.content}")
        print(f"\n🎉 可用的 Base URL: {base_url_no_v1}")
        return base_url_no_v1

    except openai.NotFoundError as e:
        print(f"❌ 404 Not Found")
        print(f"   完整 URL 可能是: {base_url_no_v1}/v1/chat/completions")
    except Exception as e:
        print(f"❌ 错误: {type(e).__name__}: {e}")

    return None


async def inspect_api_structure():
    """检查 API 的结构"""
    print("\n" + "=" * 60)
    print("检查 API 结构")
    print("=" * 60)

    base_url = settings.sss_base_url.rstrip('/')

    # 尝试访问根路径和常见路径
    test_paths = [
        base_url,
        f"{base_url}/",
        f"{base_url}/v1",
        f"{base_url}/api",
        f"{base_url}/docs",
        f"{base_url}/openapi.json",
    ]

    async with httpx.AsyncClient(timeout=10.0) as client:
        for path in test_paths:
            try:
                response = await client.get(
                    path,
                    headers={"Authorization": f"Bearer {settings.sss_api_key}"},
                )
                print(f"\nGET {path}")
                print(f"  状态码: {response.status_code}")
                if response.status_code == 200:
                    print(f"  内容: {response.text[:200]}")
            except Exception as e:
                print(f"\nGET {path}")
                print(f"  错误: {e}")


async def main():
    print("\n🔍 详细诊断 SSS Provider API 端点\n")

    # 测试 1: 直接测试不同的端点路径
    working_endpoint = await test_chat_endpoint_variants()

    # 测试 2: 使用 OpenAI 客户端测试
    if not working_endpoint:
        working_base_url = await test_with_openai_client()

    # 测试 3: 检查 API 结构
    await inspect_api_structure()

    # 总结
    print("\n" + "=" * 60)
    print("诊断总结")
    print("=" * 60)

    if working_endpoint:
        print(f"\n✅ 找到可用的端点: {working_endpoint}")
    else:
        print("\n❌ 未找到可用的 chat completions 端点")
        print("\n已知信息:")
        print("  - API Key 有效（可以获取模型列表）")
        print("  - 可用模型: gpt-5.5, claude-opus-4-7, gpt-5.4 等")
        print("  - Base URL: https://codex1.sssaicode.com/api/v1")
        print("\n建议:")
        print("  1. 联系 SSS 提供商获取正确的 API 文档")
        print("  2. 确认 chat completions 的正确端点路径")
        print("  3. 可能需要使用不同的 SDK 或 API 调用方式")


if __name__ == "__main__":
    asyncio.run(main())
