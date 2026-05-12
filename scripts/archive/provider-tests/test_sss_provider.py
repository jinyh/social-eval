#!/usr/bin/env python3
"""测试 SSS Provider 是否可以调用 GPT 5.5"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.evaluation.providers.sss_provider import SSSProvider
from src.core.config import settings


async def test_sss_provider():
    """测试 SSS Provider 基本功能"""
    print("=" * 60)
    print("测试 SSS Provider - GPT 5.5")
    print("=" * 60)

    # 检查配置
    print("\n1. 检查配置...")
    if not settings.sss_api_key:
        print("❌ 错误：未配置 SSS_API_KEY")
        print("   请在 .env 文件中设置 SSS_API_KEY")
        return False

    print(f"✅ API Key: {settings.sss_api_key[:10]}...")
    print(f"✅ Base URL: {settings.sss_base_url}")

    # 创建 provider
    print("\n2. 创建 SSSProvider...")
    provider = SSSProvider("gpt-5.5")
    print(f"✅ Provider 创建成功，模型: {provider.model_name}")

    # 测试简单的 JSON 响应
    print("\n3. 测试 JSON 响应生成...")
    test_prompt = """请以 JSON 格式回答以下问题：

问题：什么是人工智能？

要求输出格式：
{
    "answer": "你的回答",
    "confidence": 0.95
}
"""

    try:
        print("   发送请求...")
        response = await provider.generate_json_response(test_prompt)
        print("✅ 响应成功！")
        print(f"   响应内容: {response}")

        # 验证响应格式
        if "answer" in response and "confidence" in response:
            print("✅ JSON 格式正确")
        else:
            print("⚠️  警告：JSON 格式不符合预期")

        return True

    except Exception as e:
        print(f"❌ 调用失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_evaluation_dimension():
    """测试评价维度功能"""
    print("\n" + "=" * 60)
    print("测试评价维度功能")
    print("=" * 60)

    provider = SSSProvider("gpt-5.5")

    # 构造一个简单的评价 prompt
    test_prompt = """请评价以下论文片段的"问题创新性"维度：

论文片段：
"本文研究了人工智能在法律领域的应用，特别是智能合同审查系统的设计与实现。"

请按以下 JSON 格式输出评分：
{
    "dimension_name": "问题创新性",
    "score": 75,
    "reasoning": "你的评分理由",
    "confidence": 0.85
}
"""

    try:
        print("   发送评价请求...")
        result = await provider.evaluate_dimension(test_prompt)
        print("✅ 评价成功！")
        print(f"   维度: {result.dimension_name}")
        print(f"   分数: {result.score}")
        print(f"   理由: {result.reasoning[:100]}...")
        print(f"   置信度: {result.confidence}")
        print(f"   模型: {result.model_name}")

        return True

    except Exception as e:
        print(f"❌ 评价失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主测试流程"""
    print("\n🚀 开始测试 SSS Provider\n")

    # 测试 1: 基本 JSON 响应
    test1_passed = await test_sss_provider()

    # 测试 2: 评价维度功能
    test2_passed = await test_evaluation_dimension()

    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"基本 JSON 响应: {'✅ 通过' if test1_passed else '❌ 失败'}")
    print(f"评价维度功能: {'✅ 通过' if test2_passed else '❌ 失败'}")

    if test1_passed and test2_passed:
        print("\n🎉 所有测试通过！SSS Provider 可以正常使用。")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查配置和网络连接。")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
