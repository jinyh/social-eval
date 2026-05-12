#!/usr/bin/env python3
"""使用实际的模型列表测试 SSS Provider"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import openai
from src.core.config import settings


async def test_with_actual_models():
    """使用从 API 获取的实际模型名称进行测试"""
    print("=" * 60)
    print("使用实际模型列表测试 SSS Provider")
    print("=" * 60)

    client = openai.AsyncOpenAI(
        api_key=settings.sss_api_key,
        base_url=settings.sss_base_url,
        timeout=30.0,
    )

    # 1. 获取模型列表
    print("\n1. 获取可用模型...")
    try:
        models = await client.models.list()
        model_ids = [model.id for model in models.data]
        print(f"✅ 找到 {len(model_ids)} 个模型:")
        for model_id in model_ids:
            print(f"  - {model_id}")
    except Exception as e:
        print(f"❌ 获取模型列表失败: {e}")
        return

    # 2. 尝试每个模型
    print("\n2. 测试每个模型的 chat completions...")

    test_message = [{"role": "user", "content": "Hello, respond with just 'Hi'"}]

    for model_id in model_ids[:3]:  # 只测试前 3 个模型
        print(f"\n测试模型: {model_id}")
        try:
            response = await client.chat.completions.create(
                model=model_id,
                messages=test_message,
                max_tokens=10,
                temperature=0.3,
            )

            content = response.choices[0].message.content
            print(f"  ✅ 成功！响应: {content}")
            print(f"  🎉 找到可用的模型: {model_id}")
            print(f"  Base URL: {settings.sss_base_url}")
            return model_id

        except openai.NotFoundError as e:
            print(f"  ❌ 404 Not Found")
        except openai.BadRequestError as e:
            print(f"  ⚠️  400 Bad Request: {e}")
        except Exception as e:
            print(f"  ❌ 错误: {type(e).__name__}: {str(e)[:100]}")

    print("\n❌ 所有模型都测试失败")
    return None


async def test_different_base_urls():
    """测试不同的 Base URL（去掉 /api/v1 后缀）"""
    print("\n" + "=" * 60)
    print("测试不同的 Base URL 配置")
    print("=" * 60)

    # 尝试不同的 Base URL
    base_urls = [
        "https://codex1.sssaicode.com/api/v1",  # 当前配置
        "https://codex1.sssaicode.com",         # 去掉 /api/v1
        "https://codex1.sssaicode.com/api",     # 只保留 /api
    ]

    for base_url in base_urls:
        print(f"\n测试 Base URL: {base_url}")

        try:
            client = openai.AsyncOpenAI(
                api_key=settings.sss_api_key,
                base_url=base_url,
                timeout=10.0,
            )

            response = await client.chat.completions.create(
                model="gpt-5.5",
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=10,
            )

            print(f"  ✅ 成功！")
            print(f"  响应: {response.choices[0].message.content}")
            print(f"  🎉 可用的 Base URL: {base_url}")
            return base_url

        except openai.NotFoundError:
            print(f"  ❌ 404 Not Found")
        except Exception as e:
            print(f"  ❌ {type(e).__name__}: {str(e)[:80]}")

    return None


async def main():
    print("\n🔍 SSS Provider 深度测试\n")

    # 测试 1: 使用实际的模型名称
    working_model = await test_with_actual_models()

    # 测试 2: 尝试不同的 Base URL
    if not working_model:
        working_base_url = await test_different_base_urls()

    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    if working_model:
        print(f"\n✅ 找到可用配置:")
        print(f"  模型: {working_model}")
        print(f"  Base URL: {settings.sss_base_url}")
    else:
        print("\n❌ 未找到可用配置")
        print("\n请提供以下信息:")
        print("  1. 在 codex 环境中使用的完整代码示例")
        print("  2. codex 环境中的 Base URL 配置")
        print("  3. codex 环境中使用的模型名称")
        print("  4. 是否有任何特殊的请求头或参数")


if __name__ == "__main__":
    asyncio.run(main())
