"""诊断 GLM-5.1 超时问题：分维度测试响应时间，对比 qwen3.6-plus。

测试策略：
1. 用最短的 prompt（problem_innovation）测试 GLM-5.1 是否能正常返回
2. 用最长的 prompt（forward_extension）复现超时
3. 对比 qwen3.6-plus 在相同 prompt 下的响应时间
"""

import asyncio
import time
import sys
sys.path.insert(0, ".")

from src.evaluation.providers.dashscope_provider import DashScopeProvider
from src.core.config import settings


# 短 prompt：模拟 problem_innovation 维度的最小评估请求
SHORT_PROMPT = """你是一位法学论文评审专家。请评估以下论文摘要的"问题创新性"维度。

论文摘要：本文探讨了人工智能时代司法公正与同理心正义的关系，提出了一种新的理论框架。

请以 JSON 格式输出：
{"dimension": "problem_innovation", "score": 0-100的整数, "band": "excellent/good/marginal/unacceptable", "summary": "一句话总结", "core_judgment": "核心判断", "score_rationale": "评分理由", "evidence_quotes": ["证据"], "strengths": ["优点"], "weaknesses": ["不足"], "limit_rule_triggered": [], "boundary_note": null, "review_flags": ["none"]}"""

# 长 prompt：模拟 forward_extension 维度（通常包含更多上下文）
LONG_PROMPT = """你是一位法学论文评审专家。请评估以下论文的"前瞻延展性"维度。

论文全文摘要（约2000字）：
本文以"司法公正与同理心正义"为主题，系统探讨了在人工智能辅助司法决策背景下，如何平衡形式正义与实质正义的关系。文章首先回顾了西方法哲学中关于正义的经典理论，包括罗尔斯的公平正义论、德沃金的权利论以及哈贝马斯的商谈伦理。在此基础上，作者提出了"同理心正义"的概念框架，认为司法裁判不应仅仅依赖形式逻辑推理，还应当考虑当事人的具体处境和情感需求。

文章的核心论点包括：（1）传统的形式正义观在面对复杂社会纠纷时存在局限性；（2）同理心作为一种认知能力，可以帮助法官更好地理解案件的实质争议；（3）人工智能辅助决策系统应当被设计为增强而非替代法官的同理心判断能力；（4）需要建立一套制度化的机制来确保同理心正义的实现不会损害法律的确定性和可预测性。

在方法论上，本文采用了比较法学的研究路径，对比分析了中国、美国、德国三国在司法裁判中对同理心因素的处理方式。通过对典型案例的深入分析，作者发现不同法律传统对同理心的态度存在显著差异，但都在不同程度上承认了情感因素在司法决策中的正当性。

文章最后提出了"结构化同理心"的制度设计方案，包括：建立当事人陈述制度、引入社会调查报告、设置量刑前听证程序等具体措施。作者认为，这些制度设计可以在保持法律确定性的前提下，为同理心正义的实现提供制度保障。

前瞻延展性评估要求：
- 评估论文是否具有理论延展空间
- 评估研究方法是否可推广到其他领域
- 评估核心概念是否具有学术生命力
- 三前提检查：(a) base_score >= 70, (b) 无 ceiling_rule 触发, (c) 前瞻性论述有具体证据支撑

请以 JSON 格式输出：
{"dimension": "forward_extension", "score": 0-100的整数, "band": "excellent/good/marginal/unacceptable", "summary": "一句话总结", "core_judgment": "核心判断", "score_rationale": "评分理由", "evidence_quotes": ["证据1", "证据2"], "strengths": ["优点"], "weaknesses": ["不足"], "limit_rule_triggered": [], "boundary_note": null, "review_flags": ["none"]}"""


async def test_provider(model_name: str, prompt: str, label: str, timeout: float = 60.0):
    """测试单个 provider 的响应时间"""
    provider = DashScopeProvider(model_name)
    start = time.time()
    try:
        result = await asyncio.wait_for(
            provider.generate_json_response(prompt),
            timeout=timeout,
        )
        elapsed = time.time() - start
        score = result.get("score", "N/A")
        print(f"  [{label}] {model_name}: {elapsed:.1f}s, score={score}")
        return elapsed
    except asyncio.TimeoutError:
        elapsed = time.time() - start
        print(f"  [{label}] {model_name}: TIMEOUT ({elapsed:.1f}s)")
        return None
    except Exception as e:
        elapsed = time.time() - start
        print(f"  [{label}] {model_name}: ERROR ({elapsed:.1f}s) — {e}")
        return None


async def main():
    if not settings.dashscope_api_key:
        print("ERROR: DASHSCOPE_API_KEY 未配置")
        return

    print("=" * 60)
    print("GLM-5.1 诊断测试")
    print("=" * 60)

    print("\n--- 测试 1: 短 prompt (problem_innovation 模拟) ---")
    await test_provider("qwen3.6-plus", SHORT_PROMPT, "短prompt")
    await test_provider("glm-5.1", SHORT_PROMPT, "短prompt")

    print("\n--- 测试 2: 长 prompt (forward_extension 模拟) ---")
    await test_provider("qwen3.6-plus", LONG_PROMPT, "长prompt")
    await test_provider("glm-5.1", LONG_PROMPT, "长prompt", timeout=120.0)

    print("\n--- 测试 3: GLM-5.1 并发 (模拟 pipeline 场景) ---")
    tasks = [
        test_provider("glm-5.1", SHORT_PROMPT, "并发-短"),
        test_provider("glm-5.1", LONG_PROMPT, "并发-长", timeout=120.0),
    ]
    await asyncio.gather(*tasks)

    print("\n" + "=" * 60)
    print("诊断完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
