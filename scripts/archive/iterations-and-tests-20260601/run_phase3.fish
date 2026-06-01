#!/usr/bin/env fish
# Phase 3 补充论文评审 - 定时启动脚本
# 用法：
#   直接执行：fish scripts/run_phase3.fish
#   定时执行（凌晨3点）：at 3:00 < scripts/run_phase3.fish

cd /Users/jinyh/Documents/AIProjects/SocialEval

# 加载环境变量
if test -f .env
    for line in (cat .env | grep -v '^#' | grep -v '^$')
        set -x (string split '=' -- $line)
    end
end

.venv/bin/python scripts/phase2_evaluate.py \
    --paper-list results/phase3-paper-list-cleaned.json \
    --framework configs/frameworks/law-v2.55-cross-review.yaml \
    --output-dir results/phase3-evaluation \
    --concurrency 5 \
    --rounds both
