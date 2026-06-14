#!/usr/bin/env python3
"""精确定位哪个 import 卡死。"""
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

imports = [
    ("csv", "import csv"),
    ("json", "import json"),
    ("asyncio", "import asyncio"),
    ("src.knowledge.law_ontology", "from src.knowledge.law_ontology import LawOntology, load_law_ontology, parse_law_tree_markdown, write_law_ontology"),
    ("src.knowledge.candidate_validation", "from src.knowledge.candidate_validation import validate_candidate_nodes, validate_node_matches"),
    ("src.knowledge.node_retrieval", "from src.knowledge.node_retrieval import RetrievedNode, retrieve_nodes"),
    ("evaluate_top101 (整体)", "import scripts.evaluate_top101_position_assessment_two_rounds"),
    ("evaluate_fullpaper (整体)", "import scripts.evaluate_fullpaper_position_assessment"),
    ("src.evaluation.providers.factory", "from src.evaluation.providers.factory import create_providers"),
]

for label, stmt in imports:
    t0 = time.monotonic()
    print(f"→ {label} ...", end="", flush=True)
    try:
        exec(stmt)
        elapsed = time.monotonic() - t0
        print(f" {elapsed:.1f}s ✓", flush=True)
    except Exception as e:
        elapsed = time.monotonic() - t0
        print(f" {elapsed:.1f}s ✗ {e}", flush=True)

print("\n完成", flush=True)
