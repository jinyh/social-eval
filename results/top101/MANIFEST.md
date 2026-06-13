# Top101 Evaluation Manifest

This directory contains the current E2 candidate-pool summaries for the China
autonomous knowledge innovation index report.

## Current Scope

- Corpus: 1920 papers, joined by `results/merged-metadata.csv` column `编号`.
- E2 candidate pool: 101 papers.
- Selection rule: weighted Top60 + year minimum of 5 papers + discipline
  minimum of 5 papers.
- E3 selective pool: 45 papers.
- Ranking source of truth: `results/top101/ranking.json`.
- Earlier expert-review display list: `results/top101/top50-proportional.json`.
- Canonical Top50 display list under the 2026-06-13 position-first rule:
  `results/top101/top50-position-first-proportional.json`.
- Top50 selection rule adopted on 2026-06-13:
  1. Use five-axis autonomous knowledge system position score = 10 as the main
     eligibility pool.
  2. Allocate the 50 seats by the 1920-paper corpus discipline proportions.
  3. Within each discipline quota, rank eligible papers by the six-dimension
     weighted innovation score.
  4. If a discipline quota cannot be filled from 10-point papers, fill only
     from 9-point papers in the same discipline.
  5. Papers with position score <= 8 do not enter the formal Top50 by default
     and remain high-quality general-law, observation, or expert-review samples.
- Note: `top50-proportional.json` is the earlier discipline-proportional display
  artifact and is no longer canonical for the position-first Top50.

## Local Raw Outputs

The raw per-paper evaluation outputs are local-only and ignored by Git:

- `results/top101/E1/`: 101 paper JSON files.
- `results/top101/E2/`: 101 paper JSON files.
- `results/top101/E3/`: 45 paper JSON files.
- `results/top101/paper-*.json`: 101 merged per-paper JSON files.

These files are retained locally for audit and regeneration, but they are not
repository artifacts.

## Coverage Check

Year counts in the E2 pool:

| Year | Count |
|---|---:|
| 2015 | 6 |
| 2016 | 8 |
| 2017 | 6 |
| 2018 | 7 |
| 2019 | 11 |
| 2020 | 9 |
| 2021 | 11 |
| 2022 | 11 |
| 2023 | 12 |
| 2024 | 10 |
| 2025 | 10 |

Discipline counts in the E2 pool:

| Discipline | Count |
|---|---:|
| 党内法规学 | 5 |
| 刑法学 | 20 |
| 国际法学 | 5 |
| 宪法学与行政法学 | 8 |
| 数字法学 | 5 |
| 民商法学 | 19 |
| 法学理论 | 10 |
| 法律史 | 5 |
| 环境与资源保护法学 | 5 |
| 知识产权法学 | 5 |
| 经济法学 | 5 |
| 诉讼法学 | 9 |

## Regeneration

Use the local raw outputs above, then run:

```bash
python3 scripts/merge_top101.py
python3 scripts/generate_index_report_stats.py
python3 scripts/generate_top50_position_first.py
```

The report generator overlays `results/top101/ranking.json` onto the full
1920-paper baseline and rewrites the compact report artifacts under `results/`.
The Top50 generator then combines `ranking.json` with the local five-axis
position-assessment outputs under `results/top101-position-assessment-v0.2/`.
