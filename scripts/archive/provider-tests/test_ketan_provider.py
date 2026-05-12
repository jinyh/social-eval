"""KETAN Provider 集成测试脚本"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.evaluation.providers.ketan_provider import KetanProvider
from src.core.config import settings


async def test_ketan_basic_call():
    """测试 KETAN 基本调用"""
    print("=== 测试 KETAN Provider 基本调用 ===\n")

    # 检查配置
    if not settings.ketan_api_key:
        print("❌ 错误：未配置 KETAN_API_KEY")
        return False

    print(f"✓ API Key: {settings.ketan_api_key[:10]}...")
    print(f"✓ Base URL: {settings.ketan_base_url}")
    print(f"✓ Model: gpt-5.5\n")

    # 创建 provider
    provider = KetanProvider("gpt-5.5")

    # 测试简单的 JSON 生成
    test_prompt = """请以 JSON 格式返回以下信息：
{
  "dimension": "test_dimension",
  "score": 85,
  "evidence_quotes": ["这是一个测试引用"],
  "analysis": "这是一个测试分析"
}"""

    try:
        print("发送测试请求...")
        result = await provider.generate_json_response(test_prompt)
        print("✓ 成功收到响应\n")
        print("响应内容：")
        print(f"  - dimension: {result.get('dimension')}")
        print(f"  - score: {result.get('score')}")
        print(f"  - analysis: {result.get('analysis')}")
        return True
    except Exception as e:
        print(f"❌ 调用失败：{e}")
        import traceback
        traceback.print_exc()
        return False


async def test_ketan_evaluation():
    """测试 KETAN 评价功能"""
    print("\n=== 测试 KETAN Provider 评价功能 ===\n")

    provider = KetanProvider("gpt-5.5")

    # 构造一个简单的评价 prompt
    eval_prompt = """请评估以下论文片段的"问题创新性"维度（0-100分）：

论文片段：
"本文探讨了人工智能在法律领域的应用前景。"

请以 JSON 格式返回：
{
  "dimension": "问题创新性",
  "score": <0-100的分数>,
  "evidence_quotes": [<支持评分的引用>],
  "analysis": "<评分理由>"
}"""

    try:
        print("发送评价请求...")
        result = await provider.evaluate_dimension(eval_prompt)
        print("✓ 成功收到评价结果\n")
        print("评价结果：")
        print(f"  - 维度: {result.dimension}")
        print(f"  - 分数: {result.score}")
        print(f"  - 模型: {result.model_name}")
        print(f"  - 分析: {result.analysis[:100]}...")
        return True
    except Exception as e:
        print(f"❌ 评价失败：{e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主测试流程"""
    print("=" * 60)
    print("KETAN Provider 集成测试")
    print("=" * 60 + "\n")

    # 测试1：基本调用
    test1_passed = await test_ketan_basic_call()

    # 测试2：评价功能
    test2_passed = await test_ketan_evaluation()

    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"基本调用测试: {'✓ 通过' if test1_passed else '✗ 失败'}")
    print(f"评价功能测试: {'✓ 通过' if test2_passed else '✗ 失败'}")

    if test1_passed and test2_passed:
        print("\n✓ 所有测试通过！KETAN provider 工作正常。")
        return 0
    else:
        print("\n✗ 部分测试失败，请检查配置和实现。")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
