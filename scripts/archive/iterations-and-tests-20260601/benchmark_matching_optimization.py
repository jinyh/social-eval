#!/usr/bin/env python3
"""
匹配优化效果对比测试

对比原版和优化版的：
1. 关键词匹配速度
2. 语义匹配召回率
3. LLM 调用次数
4. 整体运行时间
"""

import time
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 导入原版和优化版的函数
from scripts.match_top30_papers_to_knowledge import (
    parse_knowledge_base as parse_kb_original,
    build_keyword_index as build_index_original,
    keyword_prefilter as prefilter_original,
    extract_paper_text,
)

from scripts.match_top30_papers_to_knowledge_optimized import (
    parse_knowledge_base as parse_kb_optimized,
    build_keyword_index as build_index_optimized,
    keyword_prefilter_optimized as prefilter_optimized,
    build_semantic_index,
    semantic_match,
)

from sentence_transformers import SentenceTransformer


def benchmark_keyword_matching():
    """对比关键词匹配速度"""
    print("=" * 60)
    print("测试 1：关键词匹配速度对比")
    print("=" * 60)

    # 准备数据
    knowledge_md = PROJECT_ROOT / "knowledge" / "中国法学自主知识体系-树状知识库.md"
    paper_dir = PROJECT_ROOT / "raw" / "top30_paper"
    pdf_files = sorted(paper_dir.glob("*.pdf"))[:5]  # 测试前 5 篇

    print(f"\n解析知识库...")
    knowledge = parse_kb_original(knowledge_md)

    print(f"构建索引...")
    # 原版索引
    start = time.time()
    keyword_index_original = build_index_original(knowledge)
    time_original_index = time.time() - start
    print(f"  原版索引构建：{time_original_index:.3f}s")

    # 优化版索引
    start = time.time()
    keyword_index_optimized, regex_pattern = build_index_optimized(knowledge)
    time_optimized_index = time.time() - start
    print(f"  优化版索引构建：{time_optimized_index:.3f}s")

    # 提取论文文本
    print(f"\n提取 {len(pdf_files)} 篇论文文本...")
    papers = []
    for pdf_path in pdf_files:
        try:
            text = extract_paper_text(pdf_path)
            papers.append((pdf_path.name, text))
        except Exception as e:
            print(f"  ⚠️  跳过 {pdf_path.name}：{e}")

    # 测试原版匹配速度
    print(f"\n原版关键词匹配...")
    start = time.time()
    for name, text in papers:
        result = prefilter_original(text, keyword_index_original)
    time_original_match = time.time() - start
    print(f"  耗时：{time_original_match:.3f}s")
    print(f"  平均：{time_original_match / len(papers):.3f}s/篇")

    # 测试优化版匹配速度
    print(f"\n优化版关键词匹配...")
    start = time.time()
    for name, text in papers:
        result = prefilter_optimized(text, keyword_index_optimized, regex_pattern)
    time_optimized_match = time.time() - start
    print(f"  耗时：{time_optimized_match:.3f}s")
    print(f"  平均：{time_optimized_match / len(papers):.3f}s/篇")

    # 计算加速比
    speedup = time_original_match / time_optimized_match
    print(f"\n✅ 加速比：{speedup:.1f}x")

    return {
        "original_time": time_original_match,
        "optimized_time": time_optimized_match,
        "speedup": speedup,
    }


def benchmark_semantic_matching():
    """测试语义匹配效果"""
    print("\n" + "=" * 60)
    print("测试 2：语义匹配召回率")
    print("=" * 60)

    # 准备数据
    knowledge_md = PROJECT_ROOT / "knowledge" / "中国法学自主知识体系-树状知识库.md"
    paper_dir = PROJECT_ROOT / "raw" / "top30_paper"
    pdf_files = sorted(paper_dir.glob("*.pdf"))[:3]  # 测试前 3 篇

    print(f"\n解析知识库...")
    knowledge = parse_kb_optimized(knowledge_md)

    print(f"构建关键词索引...")
    keyword_index, regex_pattern = build_index_optimized(knowledge)

    print(f"构建语义索引...")
    embedding_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    cache_path = PROJECT_ROOT / ".cache" / "embeddings" / "test_embeddings.npz"
    semantic_items, semantic_embeddings = build_semantic_index(
        knowledge, embedding_model, cache_path
    )

    # 提取论文文本
    print(f"\n提取 {len(pdf_files)} 篇论文文本...")
    papers = []
    for pdf_path in pdf_files:
        try:
            text = extract_paper_text(pdf_path)
            papers.append((pdf_path.name, text))
        except Exception as e:
            print(f"  ⚠️  跳过 {pdf_path.name}：{e}")

    # 对比关键词和语义匹配结果
    print(f"\n对比匹配结果...")
    for name, text in papers:
        print(f"\n  论文：{name[:50]}...")

        # 关键词匹配
        keyword_result = prefilter_optimized(text, keyword_index, regex_pattern)
        keyword_items = set()
        for disc_items in keyword_result["candidate_items"].values():
            for items in disc_items.values():
                keyword_items.update(items)

        # 语义匹配
        semantic_result = semantic_match(
            text, semantic_items, semantic_embeddings, embedding_model
        )
        semantic_items_set = set()
        for disc_items in semantic_result.values():
            for items in disc_items.values():
                for item, sim in items:
                    semantic_items_set.add(item)

        # 统计
        only_keyword = keyword_items - semantic_items_set
        only_semantic = semantic_items_set - keyword_items
        both = keyword_items & semantic_items_set

        print(f"    关键词匹配：{len(keyword_items)} 项")
        print(f"    语义匹配：{len(semantic_items_set)} 项")
        print(f"    两者共有：{len(both)} 项")
        print(f"    仅关键词：{len(only_keyword)} 项")
        print(f"    仅语义：{len(only_semantic)} 项")

        if only_semantic:
            print(f"    语义独有（前 3）：")
            for item in list(only_semantic)[:3]:
                print(f"      - {item}")

    return {
        "papers_tested": len(papers),
    }


def benchmark_llm_call_reduction():
    """测试 LLM 调用次数减少"""
    print("\n" + "=" * 60)
    print("测试 3：LLM 调用次数优化")
    print("=" * 60)

    # 准备数据
    knowledge_md = PROJECT_ROOT / "knowledge" / "中国法学自主知识体系-树状知识库.md"
    paper_dir = PROJECT_ROOT / "raw" / "top30_paper"
    pdf_files = sorted(paper_dir.glob("*.pdf"))[:10]  # 测试前 10 篇

    print(f"\n解析知识库...")
    knowledge = parse_kb_optimized(knowledge_md)

    print(f"构建索引...")
    keyword_index, regex_pattern = build_index_optimized(knowledge)

    print(f"构建语义索引...")
    embedding_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    cache_path = PROJECT_ROOT / ".cache" / "embeddings" / "test_embeddings.npz"
    semantic_items, semantic_embeddings = build_semantic_index(
        knowledge, embedding_model, cache_path
    )

    # 提取论文文本
    print(f"\n提取 {len(pdf_files)} 篇论文文本...")
    papers = []
    for pdf_path in pdf_files:
        try:
            text = extract_paper_text(pdf_path)
            papers.append((pdf_path.name, text))
        except Exception as e:
            print(f"  ⚠️  跳过 {pdf_path.name}：{e}")

    # 统计需要调用 LLM 的论文数
    from scripts.match_top30_papers_to_knowledge_optimized import (
        should_call_llm,
        merge_results,
    )

    llm_needed = 0
    for name, text in papers:
        keyword_result = prefilter_optimized(text, keyword_index, regex_pattern)
        semantic_result = semantic_match(
            text, semantic_items, semantic_embeddings, embedding_model
        )
        merged_result = merge_results(keyword_result, semantic_result)

        if should_call_llm(keyword_result, semantic_result):
            llm_needed += 1

    print(f"\n原版：所有论文都调用 LLM = {len(papers)} 次")
    print(f"优化版：需要调用 LLM = {llm_needed} 次")
    print(f"✅ 减少调用：{len(papers) - llm_needed} 次（{(1 - llm_needed / len(papers)) * 100:.1f}%）")

    return {
        "total_papers": len(papers),
        "llm_calls_original": len(papers),
        "llm_calls_optimized": llm_needed,
        "reduction_rate": (1 - llm_needed / len(papers)) * 100,
    }


def main():
    print("知识库匹配优化效果对比测试")
    print("=" * 60)

    results = {}

    # 测试 1：关键词匹配速度
    try:
        results["keyword_matching"] = benchmark_keyword_matching()
    except Exception as e:
        print(f"\n❌ 测试 1 失败：{e}")
        import traceback
        traceback.print_exc()

    # 测试 2：语义匹配召回率
    try:
        results["semantic_matching"] = benchmark_semantic_matching()
    except Exception as e:
        print(f"\n❌ 测试 2 失败：{e}")
        import traceback
        traceback.print_exc()

    # 测试 3：LLM 调用次数
    try:
        results["llm_reduction"] = benchmark_llm_call_reduction()
    except Exception as e:
        print(f"\n❌ 测试 3 失败：{e}")
        import traceback
        traceback.print_exc()

    # 汇总报告
    print("\n" + "=" * 60)
    print("汇总报告")
    print("=" * 60)

    if "keyword_matching" in results:
        km = results["keyword_matching"]
        print(f"\n关键词匹配加速：{km['speedup']:.1f}x")
        print(f"  原版：{km['original_time']:.3f}s")
        print(f"  优化版：{km['optimized_time']:.3f}s")

    if "llm_reduction" in results:
        lr = results["llm_reduction"]
        print(f"\nLLM 调用减少：{lr['reduction_rate']:.1f}%")
        print(f"  原版：{lr['llm_calls_original']} 次")
        print(f"  优化版：{lr['llm_calls_optimized']} 次")

    print("\n✅ 测试完成")


if __name__ == "__main__":
    main()
