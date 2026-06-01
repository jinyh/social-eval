#!/usr/bin/env python3
"""测试语义匹配效果"""

import sys
from pathlib import Path
import time

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.match_top30_papers_to_knowledge import (
    parse_knowledge_base,
    build_keyword_index,
    keyword_prefilter,
    extract_paper_text,
)

try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
    import numpy as np
    HAS_EMBEDDING = True
except ImportError:
    HAS_EMBEDDING = False
    print("⚠️  sentence-transformers 未安装，跳过语义匹配测试")


def build_semantic_index(knowledge, model):
    """构建语义索引"""
    items = []
    texts = []
    
    for disc_key, sections in knowledge.items():
        # 只对标识性概念和原创性理论做语义匹配
        for category in ["标识性概念", "原创性理论"]:
            for item in sections.get(category, []):
                items.append((disc_key, category, item))
                texts.append(item)
    
    print(f"  计算 {len(texts)} 个条目的 embedding...")
    embeddings = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    
    return items, embeddings


def semantic_match(paper_text, items, embeddings, model, threshold=0.65):
    """语义匹配"""
    # 按段落切分
    paragraphs = [p.strip() for p in paper_text.split('\n\n') if len(p.strip()) > 50]
    
    if not paragraphs:
        return {}
    
    # 计算段落 embedding
    para_embeddings = model.encode(paragraphs, show_progress_bar=False, convert_to_numpy=True)
    
    # 计算相似度
    similarities = cosine_similarity(para_embeddings, embeddings)
    max_similarities = similarities.max(axis=0)
    
    # 筛选高于阈值的匹配
    matches = []
    for idx, sim in enumerate(max_similarities):
        if sim >= threshold:
            disc_key, category, item = items[idx]
            matches.append((disc_key, category, item, sim))
    
    # 按相似度排序
    matches = sorted(matches, key=lambda x: x[3], reverse=True)[:20]
    
    # 组织成字典
    result = {}
    for disc_key, category, item, sim in matches:
        if disc_key not in result:
            result[disc_key] = {"标识性概念": [], "原创性理论": [], "框架结构": []}
        result[disc_key][category].append((item, sim))
    
    return result


def test():
    if not HAS_EMBEDDING:
        return
    
    print("=" * 60)
    print("语义匹配效果测试")
    print("=" * 60)
    
    # 准备数据
    knowledge_md = PROJECT_ROOT / "knowledge" / "中国法学自主知识体系-树状知识库.md"
    paper_dir = PROJECT_ROOT / "raw" / "top30_paper"
    
    print("\n解析知识库...")
    knowledge = parse_knowledge_base(knowledge_md)
    keyword_index = build_keyword_index(knowledge)
    
    print("\n加载 embedding 模型...")
    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    
    print("\n构建语义索引...")
    start = time.time()
    items, embeddings = build_semantic_index(knowledge, model)
    print(f"  耗时：{time.time() - start:.2f}s")
    print(f"  索引条目：{len(items)}")
    
    # 测试 3 篇论文
    pdf_files = sorted(paper_dir.glob("*.pdf"))[:3]
    
    for pdf_path in pdf_files:
        print(f"\n{'='*60}")
        print(f"论文：{pdf_path.name[:60]}")
        print(f"{'='*60}")
        
        text = extract_paper_text(pdf_path)
        print(f"文本长度：{len(text)} 字")
        
        # 关键词匹配
        print(f"\n关键词匹配：")
        kw_result = keyword_prefilter(text, keyword_index)
        kw_items = set()
        for disc_items in kw_result["candidate_items"].values():
            for items_list in disc_items.values():
                kw_items.update(items_list)
        print(f"  命中 {len(kw_items)} 个条目")
        if kw_items:
            print(f"  示例：{list(kw_items)[:5]}")
        
        # 语义匹配
        print(f"\n语义匹配：")
        start = time.time()
        sem_result = semantic_match(text, items, embeddings, model)
        print(f"  耗时：{time.time() - start:.2f}s")
        
        sem_items = set()
        for disc_items in sem_result.values():
            for items_list in disc_items.values():
                for item, sim in items_list:
                    sem_items.add(item)
        print(f"  命中 {len(sem_items)} 个条目")
        
        # 对比
        only_kw = kw_items - sem_items
        only_sem = sem_items - kw_items
        both = kw_items & sem_items
        
        print(f"\n对比分析：")
        print(f"  两者共有：{len(both)} 个")
        print(f"  仅关键词：{len(only_kw)} 个")
        print(f"  仅语义：{len(only_sem)} 个")
        
        if only_sem:
            print(f"\n  语义独有（前5个）：")
            for item in list(only_sem)[:5]:
                # 找到相似度
                for disc_items in sem_result.values():
                    for items_list in disc_items.values():
                        for it, sim in items_list:
                            if it == item:
                                print(f"    - {item} (相似度: {sim:.2f})")
                                break


if __name__ == "__main__":
    test()
