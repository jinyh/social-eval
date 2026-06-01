#!/usr/bin/env python3
"""诊断关键词匹配性能"""

import re
import time
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.match_top30_papers_to_knowledge import (
    parse_knowledge_base,
    build_keyword_index,
    extract_paper_text,
)


def diagnose():
    print("=" * 60)
    print("关键词匹配性能诊断")
    print("=" * 60)
    
    # 准备数据
    knowledge_md = PROJECT_ROOT / "knowledge" / "中国法学自主知识体系-树状知识库.md"
    knowledge = parse_knowledge_base(knowledge_md)
    keyword_index = build_keyword_index(knowledge)
    
    print(f"\n知识库统计：")
    print(f"  学科数：{len(knowledge)}")
    print(f"  关键词数：{len(keyword_index)}")
    
    # 分析关键词长度分布
    kw_lengths = [len(kw) for kw in keyword_index.keys()]
    print(f"  关键词长度：min={min(kw_lengths)}, max={max(kw_lengths)}, avg={sum(kw_lengths)/len(kw_lengths):.1f}")
    
    # 提取一篇论文
    paper_dir = PROJECT_ROOT / "raw" / "top30_paper"
    pdf_path = sorted(paper_dir.glob("*.pdf"))[0]
    text = extract_paper_text(pdf_path)
    print(f"\n测试论文：{pdf_path.name[:50]}")
    print(f"  文本长度：{len(text)} 字")
    
    # 方法1：原版（逐个 in 检查）
    print(f"\n方法1：逐个 in 检查")
    start = time.time()
    matches_v1 = []
    for kw in keyword_index.keys():
        if kw in text:
            matches_v1.append(kw)
    time_v1 = time.time() - start
    print(f"  耗时：{time_v1:.4f}s")
    print(f"  命中：{len(matches_v1)} 个关键词")
    
    # 方法2：正则批量匹配
    print(f"\n方法2：正则批量匹配")
    sorted_keywords = sorted(keyword_index.keys(), key=len, reverse=True)
    start = time.time()
    pattern = re.compile('|'.join(re.escape(kw) for kw in sorted_keywords))
    time_compile = time.time() - start
    print(f"  正则编译：{time_compile:.4f}s")
    
    start = time.time()
    matches_v2 = pattern.findall(text)
    time_match = time.time() - start
    print(f"  匹配耗时：{time_match:.4f}s")
    print(f"  命中：{len(set(matches_v2))} 个关键词")
    
    time_v2_total = time_compile + time_match
    print(f"  总耗时：{time_v2_total:.4f}s")
    
    # 方法3：预编译正则（模拟多篇论文场景）
    print(f"\n方法3：预编译正则（10篇论文）")
    papers = []
    for pdf_path in sorted(paper_dir.glob("*.pdf"))[:10]:
        try:
            papers.append(extract_paper_text(pdf_path))
        except:
            pass
    
    # 原版
    start = time.time()
    for text in papers:
        matches = []
        for kw in keyword_index.keys():
            if kw in text:
                matches.append(kw)
    time_v1_multi = time.time() - start
    print(f"  原版总耗时：{time_v1_multi:.4f}s ({time_v1_multi/len(papers):.4f}s/篇)")
    
    # 优化版（正则预编译）
    pattern = re.compile('|'.join(re.escape(kw) for kw in sorted_keywords))
    start = time.time()
    for text in papers:
        matches = pattern.findall(text)
    time_v2_multi = time.time() - start
    print(f"  优化版总耗时：{time_v2_multi:.4f}s ({time_v2_multi/len(papers):.4f}s/篇)")
    
    speedup = time_v1_multi / time_v2_multi
    print(f"\n  加速比：{speedup:.2f}x")
    
    # 结论
    print(f"\n{'='*60}")
    print("结论：")
    if speedup > 1.5:
        print(f"  ✅ 优化有效！加速 {speedup:.1f}x")
    elif speedup > 1.0:
        print(f"  ⚠️  轻微加速 {speedup:.1f}x，但不明显")
    else:
        print(f"  ❌ 优化无效，反而变慢 {1/speedup:.1f}x")
        print(f"  原因：正则编译开销（{time_compile:.4f}s）> 节省的匹配时间")
    print(f"{'='*60}")


if __name__ == "__main__":
    diagnose()
