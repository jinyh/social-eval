#!/usr/bin/env python3
"""
Generate final Top 20 ranking combining Tier 1 and retested papers
"""
import json
import csv
from pathlib import Path

def load_metadata():
    """Load paper metadata"""
    metadata = {}
    csv_path = Path("results/datasets/three-journals/metadata.csv")
    with open(csv_path, 'r', encoding='utf-8-sig') as f:  # utf-8-sig handles BOM
        reader = csv.DictReader(f)
        for row in reader:
            paper_id = int(row['编号'])
            metadata[paper_id] = row['题目']
    return metadata

def load_report():
    """Load retest report"""
    report_path = Path("results/retest-top60/report.json")
    with open(report_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def generate_final_ranking():
    """Generate final Top 20 ranking"""
    metadata = load_metadata()
    report = load_report()

    # Tier 1 papers (direct selection)
    tier1_ids = report['tier1_ids']
    tier1_papers = []
    for pid in tier1_ids:
        title = metadata.get(pid, f"Paper {pid}")
        tier1_papers.append({
            'paper_id': pid,
            'title': title,
            'final_score': None,  # Will be filled from original R2 data
            'confidence': 'N/A',
            'status': 'TIER1',
            'tier': 1
        })

    # Get Tier 1 original scores from fullevaluation
    for paper in tier1_papers:
        pid = paper['paper_id']
        orig_path = Path(f"results/datasets/three-journals/six-dimension/phase2-r2-v2.55/per-paper/paper-{pid}.json")
        if orig_path.exists():
            with open(orig_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                paper['final_score'] = round(data['overall']['round2_final_score_mean'], 2)

    # Tier 2-4 papers (retested)
    retested_papers = []
    for pid_str, score_data in report['final_scores'].items():
        pid = int(pid_str.replace('paper-', ''))
        title = metadata.get(pid, f"Paper {pid}")
        confidence = report['confidence_summary'][pid_str]['overall_confidence']

        retested_papers.append({
            'paper_id': pid,
            'title': title,
            'final_score': score_data['final_score'],
            'confidence': confidence,
            'status': score_data['status'],
            'tier': 2 if pid_str in ['paper-1865', 'paper-1023', 'paper-1860', 'paper-1606',
                                     'paper-1168', 'paper-1218', 'paper-1571', 'paper-901',
                                     'paper-1586', 'paper-319', 'paper-1194'] else
                     3 if pid_str in ['paper-1493', 'paper-1510', 'paper-1337', 'paper-21',
                                     'paper-1820', 'paper-1885', 'paper-1919', 'paper-619',
                                     'paper-956', 'paper-1501', 'paper-1553', 'paper-1602',
                                     'paper-1763', 'paper-1711', 'paper-1824', 'paper-1852',
                                     'paper-1575', 'paper-1450', 'paper-1779', 'paper-1864',
                                     'paper-1618', 'paper-1519'] else 4
        })

    # Combine all papers and sort by final_score
    all_papers = tier1_papers + retested_papers
    all_papers.sort(key=lambda x: x['final_score'] if x['final_score'] else 0, reverse=True)

    # Select Top 20
    top20 = all_papers[:20]

    # Generate report
    print("=" * 120)
    print("FINAL TOP 20 RANKING")
    print("=" * 120)
    print(f"{'Rank':<6} {'ID':<8} {'Tier':<6} {'Status':<12} {'Confidence':<12} {'Score':<8} {'Title'}")
    print("=" * 120)

    for i, paper in enumerate(top20, 1):
        title_short = paper['title'][:50] + "..." if len(paper['title']) > 50 else paper['title']
        print(f"{i:<6} {paper['paper_id']:<8} {paper['tier']:<6} {paper['status']:<12} "
              f"{paper['confidence']:<12} {paper['final_score']:<8} {title_short}")

    print("=" * 120)

    # Summary statistics
    needs_r3 = [p for p in all_papers if p['status'] == 'NEEDS_R3']
    warn = [p for p in all_papers if p['status'] == 'WARN']

    print(f"\nSummary:")
    print(f"  Total papers analyzed: {len(all_papers)}")
    print(f"  Tier 1 (direct): {len(tier1_papers)}")
    print(f"  Tier 2-4 (retested): {len(retested_papers)}")
    print(f"  NEEDS_R3: {len(needs_r3)} papers")
    print(f"  WARN: {len(warn)} papers")

    if needs_r3:
        print(f"\nPapers requiring R3:")
        for p in needs_r3:
            title_short = p['title'][:60] + "..." if len(p['title']) > 60 else p['title']
            print(f"  - Paper {p['paper_id']}: {title_short} (Score: {p['final_score']})")

    # Save detailed report
    output = {
        'top20': top20,
        'all_papers': all_papers,
        'summary': {
            'total': len(all_papers),
            'tier1': len(tier1_papers),
            'tier2_4': len(retested_papers),
            'needs_r3': len(needs_r3),
            'warn': len(warn)
        }
    }

    output_path = Path("results/retest-top60/final_ranking.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nDetailed ranking saved to: {output_path}")

    return output

if __name__ == "__main__":
    generate_final_ranking()
