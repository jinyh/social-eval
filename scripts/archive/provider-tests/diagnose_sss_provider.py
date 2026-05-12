#!/usr/bin/env python3
"""诊断 SSS Provider 的 API 配置"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import openai
from src.core.config import settings


async def test_base_url_variants():
    """测试不同的 Base URL 变体"""
    print("=" * 60)
    print("SSS Provider API 端点诊断")
    print("=" * 60)

    print(f"\n当前配置:")
    print(f"  API Key: {settings.sss_api_key[:15]}...")
    print(f"  Base URL: {settings.sss_base_url}")

    # 可能的 URL 变体
    url_variants = [
        settings.sss_base_url,  # 当前配置的 URL
        settings.sss_base_url.rstrip('/'),  # 去掉末尾斜杠
        settings.sss_base_url.rstrip('/v1'),  # 去掉 /v1
        settings.sss_base_url.replace('/api/v1', '/v1'),  # 替换路径
        settings.sss_base_url.replace('/v1', ''),  # 完全去掉版本号
    ]

    # 去重
    url_variants = list(dict.fromkeys(url_variants))

    print(f"\n将测试以下 {len(url_variants)} 个 URL 变体:")
    for i, url in enumerate(url_variants, 1):
        print(f"  {i}. {url}")

    print("\n开始测试...\n")

    for i, base_url in enumerate(url_variants, 1):
        print(f"[{i}/{len(url_variants)}] 测试: {base_url}")

        try:
            client = openai.AsyncOpenAI(
                api_key=settings.sss_api_key,
                base_url=base_url,
                timeout=10.0,
            )

            response = await client.chat.completions.create(
                model="gpt-5.5",
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=10,
            )

            print(f"  ✅ 成功！响应: {response.choices[0].message.content}")
            print(f"\n🎉 找到可用的 Base URL: {base_url}")
            return base_url

        except openai.NotFoundError as e:
            print(f"  ❌ 404 Not Found")
        except openai.AuthenticationError as e:
            print(f"  ⚠️  认证错误（但端点存在）: {e}")
            print(f"     这个 URL 可能是正确的，但 API Key 有问题")
        except openai.APIConnectionError as e:
            print(f"  ❌ 连接错误: {e}")
        except Exception as e:
            print(f"  ❌ 其他错误: {type(e).__name__}: {e}")

        print()

    print("❌ 所有 URL 变体都失败了")
    return None


async def test_model_list():
    """尝试获取模型列表"""
    print("=" * 60)
    print("尝试获取可用模型列表")
    print("=" * 60)

    try:
        client = openai.AsyncOpenAI(
            api_key=settings.sss_api_key,
            base_url=settings.sss_base_url,
        )

        models = await client.models.list()
        print("\n✅ 可用模型:")
        for model in models.data:
            print(f"  - {model.id}")

    except Exception as e:
        print(f"\n❌ 无法获取模型列表: {e}")


async def main():
    print("\n🔍 开始诊断 SSS Provider\n")

    # 测试 1: 尝试不同的 Base URL
    working_url = await test_base_url_variants()

    # 测试 2: 尝试获取模型列表
    await test_model_list()

    # 总结
    print("\n" + "=" * 60)
    print("诊断总结")
    print("=" * 60)

    if working_url:
        print(f"\n✅ 找到可用的 Base URL: {working_url}")
        print(f"\n请在 .env 文件中更新:")
        print(f"SSS_BASE_URL={working_url}")
    else:
        print("\n❌ 未找到可用的 Base URL")
        print("\n建议:")
        print("1. 检查 SSS 的 API 文档，确认正确的 Base URL")
        print("2. 确认 API Key 是否有效")
        print("3. 确认模型名称是否正确（可能不是 'gpt-5.5'）")
        print("4. 检查网络连接和防火墙设置")


if __name__ == "__main__":
    asyncio.run(main())
