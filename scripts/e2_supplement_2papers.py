#!/usr/bin/env python3
"""E2 补跑 2 篇 (PID 29, 1621) → results/e2-top102/"""
import asyncio, json, statistics, sys, time, logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.run_convergence_test import run_convergence_test
from scripts.run_cross_review import build_cross_review_prompt, A_GROUP, B_GROUP
from src.evaluation.providers.factory import create_providers
from src.ingestion.preprocessor import process_file
from src.knowledge.loader import _normalize_framework_data, DEFAULT_STD_THRESHOLD
from src.knowledge.schemas import Framework
import yaml

FRAMEWORK_PATH = "configs/frameworks/law-v2.55-cross-review.yaml"
MODELS = A_GROUP + B_GROUP
R1_DIR = Path("results/e2-top102/round1")
R2_DIR = Path("results/e2-top102/round2")
PIDS = [29, 1621]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

def load_fw():
    d = yaml.safe_load(Path(FRAMEWORK_PATH).read_text(encoding="utf-8"))
    if "std_threshold" not in d: d["std_threshold"] = DEFAULT_STD_THRESHOLD
    return Framework(**_normalize_framework_data(d))

def pdf_path(pid):
    with open(f"results/fullevaluation/round2/paper-{pid}.json") as f:
        return json.load(f)["paper"]

async def r1(pid, pp, sem):
    out = R1_DIR / f"paper-{pid}.json"
    if out.exists():
        log.info(f"[R1] PID {pid} skip"); return json.loads(out.read_text())
    async with sem:
        log.info(f"[R1] PID {pid} start")
        t = time.time()
        r = await run_convergence_test(FRAMEWORK_PATH, pp, MODELS, aggregation_mode="both")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info(f"[R1] PID {pid} done ({time.time()-t:.0f}s)"); return r

async def r2(pid, pp, r1res, fw, provs, sem):
    out = R2_DIR / f"paper-{pid}.json"
    if out.exists():
        log.info(f"[R2] PID {pid} skip"); return json.loads(out.read_text())
    async with sem:
        log.info(f"[R2] PID {pid} start")
        t = time.time()
        paper = process_file(pp)
        res = {"paper": pp, "paper_id": pid, "framework": FRAMEWORK_PATH,
               "models": MODELS, "dimensions": {}, "overall": {}}
        for dim in fw.dimensions:
            r1d = r1res.get("dimensions", {}).get(dim.key)
            if not r1d: continue
            raw = r1d.get("raw_outputs", {})
            r1s = {m: raw[m].get("score", 0) for m in MODELS if m in raw}
            r2s = {}
            for model in MODELS:
                if model not in raw: continue
                oth = B_GROUP if model in A_GROUP else A_GROUP
                oo = [raw[m] for m in oth if m in raw]
                if not oo: continue
                pr = provs.get(model)
                if not pr: continue
                try:
                    resp = await pr.generate_json_response(
                        build_cross_review_prompt(dim.name_zh, dim.key, raw[model], oo, paper))
                    v = resp.get("revised_score")
                    if v is not None: r2s[model] = int(v)
                except Exception as e:
                    log.warning(f"[R2] {pid} {dim.key} {model}: {e}")
            if r2s:
                res["dimensions"][dim.key] = {
                    "dimension": dim.key, "name_zh": dim.name_zh,
                    "round1_scores": r1s, "round2_scores": r2s,
                    "round1_mean": round(statistics.mean(r1s.values()), 1) if r1s else 0,
                    "round2_mean": round(statistics.mean(r2s.values()), 1),
                    "round1_std": round(statistics.stdev(r1s.values()), 1) if len(r1s) > 1 else 0,
                    "round2_std": round(statistics.stdev(r2s.values()), 1) if len(r2s) > 1 else 0,
                }
        if res["dimensions"]:
            res["overall"] = {
                "round1_avg_std": round(statistics.mean(d["round1_std"] for d in res["dimensions"].values()), 2),
                "round2_avg_std": round(statistics.mean(d["round2_std"] for d in res["dimensions"].values()), 2),
            }
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
        o = res.get("overall", {})
        log.info(f"[R2] PID {pid} R1_std={o.get('round1_avg_std','?')} R2_std={o.get('round2_avg_std','?')} ({time.time()-t:.0f}s)")
        return res

async def main():
    fw = load_fw()
    provs = {p.model_name: p for p in create_providers(MODELS)}
    sem = asyncio.Semaphore(5)
    log.info(f"=== E2 补跑 {PIDS} ===")
    t0 = time.time()
    for pid in PIDS:
        pp = pdf_path(pid)
        r = await r1(pid, pp, sem)
        if r: await r2(pid, pp, r, fw, provs, sem)
    log.info(f"=== 完成 ({(time.time()-t0)/60:.1f} min) ===")

if __name__ == "__main__":
    asyncio.run(main())
