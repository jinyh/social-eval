#!/usr/bin/env python3
"""最终测试：尝试所有可能的 SSS API 路径"""
import asyncio
import sys
from pathlib import Path
import httpx
import json

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.config import settings


async def test_all_possible_paths():
    """测试所有可能的 API 路径组合"""
    print("=" * 60)
    print("测试所有可能的 SSS API 路径")
    print("=" * 60)

    # 基础 URL 变体
    base_urls = [
        "https://codex1.sssaicode.com",
        "https://codex1.sssaicode.com/api",
        "https://codex1.sssaicode.com/api/v1",
        "https://codex1.sssaicode.com/v1",
    ]

    # 端点路径变体
    endpoints = [
        "/chat/completions",
        "/v1/chat/completions",
        "/openai/chat/completions",
        "/openai/v1/chat/completions",
        "/api/chat/completions",
        "/api/v1/chat/completions",
        "/completions",
        "/v1/completions",
    ]

    test_payload = {
        "model": "gpt-5.5",
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 10,
    }

    headers = {
        "Authorization": f"Bearer {settings.sss_api_key}",
        "Content-Type": "application/json",
    }

    print(f"\n将测试 {len(base_urls)} x {len(endpoints)} = {len(base_urls) * len(endpoints)} 个组合\n")

    successful_urls = []

    async with httpx.AsyncClient(timeout=10.0) as client:
        for base_url in base_urls:
            for endpoint in endpoints:
                # 组合 URL，避免重复的斜杠
                full_url = base_url.rstrip('/') + '/' + endpoint.lstrip('/')

                try:
                    response = await client.post(
                        full_url,
                        headers=headers,
                        json=test_payload,
                    )

                    if response.status_code == 200:
                        print(f"✅ {full_url}")
                        print(f"   响应: {response.text[:100]}")
                        successful_urls.append(full_url)
                    elif response.status_code != 404:
                        print(f"⚠️  {full_url} - 状态码: {response.status_code}")
                        print(f"   响应: {response.text[:100]}")

                except Exception as e:
                    pass  # 静默失败，只显示成功的

    return successful_urls


async def check_api_documentation():
    """尝试查找 API 文档"""
    print("\n" + "=" * 60)
    print("查找 API 文档")
    print("=" * 60)

    doc_urls = [
        "https://codex1.sssaicode.com/docs",
        "https://codex1.sssaicode.com/api/docs",
        "https://codex1.sssaicode.com/swagger",
        "https://codex1.sssaicode.com/api/swagger",
        "https://codex1.sssaicode.com/openapi.json",
        "https://codex1.sssaicode.com/api/openapi.json",
        "https://sssaicode.com/docs",
        "https://sssaicode.com/api-docs",
    ]

    async with httpx.AsyncClient(timeout=10.0) as client:
        for url in doc_urls:
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    print(f"\n✅ 找到文档: {url}")
                    print(f"   内容类型: {response.headers.get('content-type')}")
                    if 'json' in response.headers.get('content-type', ''):
                        print(f"   内容: {response.text[:200]}")
            except Exception:
                pass


async def test_alternative_request_formats():
    """测试不同的请求格式"""
    print("\n" + "=" * 60)
    print("测试不同的请求格式")
    print("=" * 60)

    base_url = "https://codex1.sssaicode.com/api/v1"

    # 测试不同的请求体格式
    test_cases = [
        {
            "name": "标准 OpenAI 格式",
            "payload": {
                "model": "gpt-5.5",
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 10,
            }
        },
        {
            "name": "简化格式",
            "payload": {
                "model": "gpt-5.5",
                "prompt": "Hello",
                "max_tokens": 10,
            }
        },
        {
            "name": "带 stream 参数",
            "payload": {
                "model": "gpt-5.5",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
            }
        },
    ]

    async with httpx.AsyncClient(timeout=10.0) as client:
        for test_case in test_cases:
            print(f"\n测试: {test_case['name']}")
            try:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.sss_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=test_case['payload'],
                )
                print(f"  状态码: {response.status_code}")
                if response.status_code == 200:
                    print(f"  ✅ 成功！")
                    print(f"  响应: {response.text[:200]}")
                else:
                    print(f"  响应: {response.text[:100]}")
            except Exception as e:
                print(f"  ❌ 错误: {e}")


async def main():
    print("\n🔍 SSS Provider 最终诊断\n")

    # 测试 1: 尝试所有可能的路径
    successful_urls = await test_all_possible_paths()

    # 测试 2: 查找 API 文档
    await check_api_documentation()

    # 测试 3: 测试不同的请求格式
    await test_alternative_request_formats()

    # 总结
    print("\n" + "=" * 60)
    print("最终总结")
    print("=" * 60)

    if successful_urls:
        print(f"\n✅ 找到 {len(successful_urls)} 个可用的端点:")
        for url in successful_urls:
            print(f"  - {url}")
    else:
        print("\n❌ 未找到任何可用的 chat completions 端点")
        print("\n结论:")
        print("  SSS 的 API 可能:")
        print("  1. 不支持 OpenAI 兼容的 chat completions 接口")
        print("  2. 使用完全不同的 API 结构")
        print("  3. 需要特殊的认证或请求头")
        print("  4. 仅支持模型列表查询，不支持实际推理")
        print("\n建议:")
        print("  - 联系 SSS 提供商获取正确的 API 文档")
        print("  - 询问是否有 Python SDK 或示例代码")
        print("  - 确认该 API Key 是否有推理权限")


if __name__ == "__main__":
    asyncio.run(main())
