"""Step 5 – experiments: alpha sweep, ablation, noise robustness, hold-out alpha tuning."""
from __future__ import annotations
import csv, random, sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import eval.run_evaluation as ev
from db.config_loader import load_config, get_path
from fusion.impact import impact_by_query
from fusion.prioritize import load_fix_data
from eval.ground_truth import ideal_scores

def impact_of(sample, conf_weight=True):
    return impact_by_query((p["pred_query_id"], float(p["pred_confidence"]) if conf_weight else 1.0, int(p["pred_severity"])) for p in sample)

def ci(v): return float(np.mean(v)), float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))

def main():
    ev.FIX, ev.EFFORT = load_fix_data()
    cfg = load_config(); k, alpha0 = cfg["eval"]["top_k"], cfg["fusion"]["alpha"]
    diag, labels, preds = ev.load_csv(get_path("diagnostics")), ev.load_csv(get_path("labels")), ev.load_csv(get_path("predictions"))
    lab = {r["complaint_id"]: r for r in labels}; n = len(preds); rd = Path(get_path("results_dir")); rd.mkdir(parents=True, exist_ok=True)
    rng, py = np.random.default_rng(1), random.Random(1)
    B = 300
    def resample():
        s = [preds[i] for i in rng.integers(0, n, n)]
        return s, ideal_scores([lab[p["complaint_id"]] for p in s])
    def score(sample, pain, a=alpha0, conf=True):
        sc = ev.method_scores(diag, impact_of(sample, conf), a, py)
        return sc

    # ---- 1) alpha sweep ----
    alphas = cfg["eval"]["alpha_sweep"]; res = {a: {"fused": [], "fused_measured": [], "bp_f": [], "bp_m": []} for a in alphas}
    for _ in range(B):
        s, pain = resample(); imp = impact_of(s)
        for a in alphas:
            sc = ev.method_scores(diag, imp, a, py)
            for m, key, bp in (("fused", "fused", "bp_f"), ("fused_measured", "fused_measured", "bp_m")):
                r = ev.order(sc[m]); res[a][key].append(ev.ndcg_at_k(r, pain, k)); res[a][bp].append(ev.budget_pain(r, pain))
    print("\n[1] alpha sweep – NDCG@%d, mean [95%% CI]  (alpha=1 is technical-only, alpha=0 is impact-only)" % k)
    rows = []
    for a in alphas:
        f, m = ci(res[a]["fused"]), ci(res[a]["fused_measured"])
        print(f"  alpha={a:.1f}  fused {f[0]:.3f} [{f[1]:.3f},{f[2]:.3f}]   fused_measured {m[0]:.3f} [{m[1]:.3f},{m[2]:.3f}]")
        rows.append({"alpha": a, "fused": f[0], "fused_lo": f[1], "fused_hi": f[2], "meas": m[0], "meas_lo": m[1], "meas_hi": m[2],
                     "budget_fused": np.mean(res[a]["bp_f"]), "budget_meas": np.mean(res[a]["bp_m"])})
    plt.figure(figsize=(7, 4.4))
    for key, lo, hi, lbl in (("fused", "fused_lo", "fused_hi", "fused (heuristic tech score)"), ("meas", "meas_lo", "meas_hi", "fused_measured (real latency gain)")):
        plt.plot(alphas, [r[key] for r in rows], marker="o", label=lbl)
        plt.fill_between(alphas, [r[lo] for r in rows], [r[hi] for r in rows], alpha=.15)
    plt.xlabel("α  (weight on technical signal)"); plt.ylabel(f"NDCG@{k}"); plt.title("α-sweep: where does user impact start to help?")
    plt.grid(alpha=.3); plt.legend(); plt.tight_layout(); plt.savefig(rd / "alpha_sweep.png", dpi=120); plt.close()
    with open(rd / "alpha_sweep.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

    # ---- 2) ablation ----
    variants = {"tech only": lambda sc, imp: sc["tech_score"], "impact only": lambda sc, imp: dict(imp) | {q: imp.get(q, 0) for q in sc["tech_score"]},
                "fused": lambda sc, imp: sc["fused"], "fused, no confidence weighting": None,
                "fused_measured": lambda sc, imp: sc["fused_measured"], "fused_effort": lambda sc, imp: sc["fused_effort"], "rrf": lambda sc, imp: sc["rrf"]}
    out = {v: {"ndcg": [], "pain": [], "bp": []} for v in variants}
    for _ in range(B):
        s, pain = resample(); imp = impact_of(s); sc = ev.method_scores(diag, imp, alpha0, py)
        sc_nc = ev.method_scores(diag, impact_of(s, conf_weight=False), alpha0, py)
        for v, fn in variants.items():
            scores = sc_nc["fused"] if fn is None else fn(sc, imp)
            r = ev.order({q: scores.get(q, 0.0) for q in sc["tech_score"]})
            out[v]["ndcg"].append(ev.ndcg_at_k(r, pain, k)); out[v]["pain"].append(ev.pain_resolved_at_k(r, pain, k)); out[v]["bp"].append(ev.budget_pain(r, pain))
    print("\n[2] ablation (alpha=%.1f)" % alpha0)
    print(f"  {'variant':34s}{'NDCG@k':>24s}{'pain@k':>24s}{'budget pain':>24s}")
    arows = []
    for v, d in out.items():
        c = {m: ci(d[m]) for m in d}
        print(f"  {v:34s}" + "".join(f"{c[m][0]:8.3f} [{c[m][1]:.3f},{c[m][2]:.3f}] " for m in ("ndcg", "pain", "bp")))
        arows.append({"variant": v, **{f"{m}_{x}": c[m][i] for m in c for i, x in enumerate(("mean", "lo", "hi"))}})
    with open(rd / "ablation.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(arows[0])); w.writeheader(); w.writerows(arows)

    # ---- 3) noise robustness: corrupt a share of complaint→query links ----
    qids = [r["query_id"] for r in diag]; levels = cfg["eval"]["noise_levels"]; nrows = []
    pain_full = ideal_scores(labels)
    for lv in levels:
        vals = {"tech only": [], "fused": [], "fused_measured": []}
        for _ in range(100):
            s = [dict(p) for p in preds]
            for p in s:
                if py.random() < lv: p["pred_query_id"] = py.choice(qids)
            sc = ev.method_scores(diag, impact_of(s), alpha0, py)
            for name, m in (("tech only", "tech_score"), ("fused", "fused"), ("fused_measured", "fused_measured")):
                vals[name].append(ev.ndcg_at_k(ev.order(sc[m]), pain_full, k))
        nrows.append({"noise": lv, **{f"{m}": np.mean(v) for m, v in vals.items()}, **{f"{m}_sd": np.std(v) for m, v in vals.items()}})
    print("\n[3] noise robustness – NDCG@%d when a share of complaint→query links is randomised" % k)
    for r in nrows: print(f"  noise={r['noise']:.1f}  tech {r['tech only']:.3f}   fused {r['fused']:.3f} (±{r['fused_sd']:.3f})   fused_measured {r['fused_measured']:.3f}")
    plt.figure(figsize=(6.5, 4.2))
    for m in ("tech only", "fused", "fused_measured"):
        plt.errorbar([r["noise"] for r in nrows], [r[m] for r in nrows], yerr=[r[m + "_sd"] for r in nrows], marker="o", capsize=3, label=m)
    plt.xlabel("Share of complaint links corrupted"); plt.ylabel(f"NDCG@{k}"); plt.title("Robustness to NLP errors"); plt.grid(alpha=.3); plt.legend(); plt.tight_layout()
    plt.savefig(rd / "noise_robustness.png", dpi=120); plt.close()
    with open(rd / "noise_robustness.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(nrows[0])); w.writeheader(); w.writerows(nrows)

    # ---- 4) hold-out alpha tuning (70/30, repeated) ----
    gains, chosen = [], []
    for _ in range(100):
        idx = list(range(n)); py.shuffle(idx); cut = int(.7 * n)
        tr, te = [preds[i] for i in idx[:cut]], [preds[i] for i in idx[cut:]]
        ptr, pte = ideal_scores([lab[p["complaint_id"]] for p in tr]), ideal_scores([lab[p["complaint_id"]] for p in te])
        itr, ite = impact_of(tr), impact_of(te)
        best = max(alphas, key=lambda a: ev.ndcg_at_k(ev.order(ev.method_scores(diag, itr, a, py)["fused"]), ptr, k))
        chosen.append(best)
        f = lambda a: ev.ndcg_at_k(ev.order(ev.method_scores(diag, ite, a, py)["fused"]), pte, k)
        gains.append((f(best), f(alpha0), f(1.0)))
    g = np.array(gains)
    print(f"\n[4] hold-out (70/30 ×100): alpha tuned on train → test NDCG@{k} = {g[:,0].mean():.3f};  fixed alpha={alpha0} → {g[:,1].mean():.3f};  tech-only → {g[:,2].mean():.3f}")
    print(f"    chosen alpha: mean {np.mean(chosen):.2f}, range {min(chosen)}–{max(chosen)}")

if __name__ == "__main__":
    main()
