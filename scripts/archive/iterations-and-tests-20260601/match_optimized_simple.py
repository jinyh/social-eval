#!/usr/bin/env python3
"""
优化版匹配脚本 - 仅实现方案A（正则批量匹配）

对比原版的逐个 in 检查，使用正则一次性匹配所有关键词
"""

import re
import time
from pathlib import Path
import sys

# 添加项目路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.match_top30_papers_to_knowledge import (
    parse_knowledge_base,
    build_keyword_index,
    extract_paper_text,
)


def build_keyword_index_optimized(knowledge: dict):
    """构建关键词索引 + 正则模式"""
    # 复用原版的索引构建
    from scripts.match_top30_papers_to_knowledge import _generate_keywords
    
    index = {}
    for disc_key, sections in knowledge.items():
        for category, items in sections.items():
            for item in items:
                keywords = _generate_keywords(item)
                for kw in keywords:
                    if kw not in index:
                        index[kw] = []
                    index[kw].append((disc_key, category, item))
    
    # 构建正则模式（按长度降序，避免短词优先匹配）
    sorted_keywords = sorted(index.keys(), key=len, reverse=True)
    pattern = re.compile('|'.join(re.escape(kw) for kw in sorted_keywords))
    
    return index, pattern


def keyword_prefilter_optimized(text: str, keyword_index: dict, regex_pattern):
    """优化版关键词预筛：使用正则批量匹配"""
    # 一次性找到所有匹配
    matches = regex_pattern.findall(text)
    
    # 统计
    disc_hits = {}
    disc_items = {}
    
    for kw in set(matches):  # 去重
        if kw in keyword_index:
            for disc_key, category, item in keyword_index[kw]:
                disc_hits[disc_key] = disc_hits.get(disc_key, 0) + 1
                if disc_key not in disc_items:
                    disc_items[disc_key] = {
                        "标识性概念": set(),
                        "原创性理论": set(),
                        "框架结构": set()
                    }
                disc_items[disc_key][category].add(item)
    
    # 排序取 Top-5
    sorted_discs = sorted(disc_hits.items(), key=lambda x: x[1], reverse=True)[:5]
    
    candidate_items = {}
    for disc_key in dict(sorted_discs):
        candidate_items[disc_key] = {
            cat: sorted(items) 
            for cat, items in disc_items.get(disc_key, {}).items()
        }
    
    return {
        "top_disciplines": sorted_discs,
        "candidate_items": candidate_items,
    }


def benchmark():
    """对比测试"""
    print("=" * 60)
    print("关键词匹配优化对比测试")
    print("=" * 60)
    
    # 准备数据
    knowledge_md = PROJECT_ROOT / "knowledge" / "中国法学自主知识体系-树状知识库.md"
    paper_dir = PROJECT_ROOT / "raw" / "top30_paper"
    
    print("\n解析知识库...")
    knowledge = parse_knowledge_base(knowledge_md)
    
    print("构建索引...")
    # 原版索引
    start = time.time()
    keyword_index_original = build_keyword_index(knowledge)
    time_original_index = time.time() - start
    print(f"  原版索引：{time_original_index:.3f}s")
    
    # 优化版索引
    start = time.time()
    keyword_index_opt, regex_pattern = build_keyword_index_optimized(knowledge)
    time_opt_index = time.time() - start
    print(f"  优化版索引：{time_opt_index:.3f}s")
    
    # 提取论文
    pdf_files = sorted(paper_dir.glob("*.pdf"))[:30]  # 测试全部 30 篇
    print(f"\n提取 {len(pdf_files)} 篇论文...")
    papers = []
    for pdf_path in pdf_files:
        try:
            text = extract_paper_text(pdf_path)
            papers.append((pdf_path.name, text))
        except Exception as e:
            print(f"  ✗ {pdf_path.name}: {e}")
    print(f"  ✓ 成功提取 {len(papers)} 篇")
    
    # 原版匹配
    print(f"\n原版匹配...")
    from scripts.match_top30_papers_to_knowledge import keyword_prefilter
    
    start = time.time()
    for name, text in papers:
        result = keyword_prefilter(text, keyword_index_original)
    time_original = time.time() - start
    print(f"  耗时：{time_original:.3f}s")
    print(f"  平均：{time_original / len(papers):.3f}s/篇")
    
    # 优化版匹配
    print(f"\n优化版匹配...")
    start = time.time()
    for name, text in papers:
        result = keyword_prefilter_optimized(text, keyword_index_opt, regex_pattern)
    time_opt = time.time() - start
    print(f"  耗时：{time_opt:.3f}s")
    print(f"  平均：{time_opt / len(papers):.3f}s/篇")
    
    # 结果
    speedup = time_original / time_opt
    print(f"\n{'='*60}")
    print(f"✅ 加速比：{speedup:.1f}x")
    print(f"{'='*60}")


if __name__ == "__main__":
    benchmark()
