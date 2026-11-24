"""Scores the label-free NLP output against the hidden labels.csv."""
from __future__ import annotations
import csv, sys
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
from sklearn.metrics import adjusted_rand_score
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.config_loader import get_path

def load(path):
    with open(path, encoding="utf-8") as f: return list(csv.DictReader(f))

def nlp_metrics(preds, labels):
    lab = {r["complaint_id"]: r for r in labels}
    ids = [p["complaint_id"] for p in preds]
    truth = [lab[i]["true_query_id"] for i in ids]
    cl = [p["topic_cluster"] for p in preds]
    ari = adjusted_rand_score(truth, cl)
    groups = defaultdict(list)
    for c, t in zip(cl, truth): groups[c].append(t)
    purity = sum(Counter(v).most_common(1)[0][1] for v in groups.values()) / len(preds)
    real = [(p["pred_query_id"], t) for p, t in zip(preds, truth) if t != "NOISE"]
    link_acc = sum(1 for p, t in real if p == t) / len(real)
    noise = [p["pred_query_id"] for p, t in zip(preds, truth) if t == "NOISE"]
    noise_rejected = sum(1 for p in noise if p == "") / max(1, len(noise))
    sev_rho = spearmanr([int(p["pred_severity"]) for p in preds], [int(lab[i]["severity_label"]) for i in ids])[0]
    return {"ARI": ari, "purity": purity, "link_accuracy(non-noise complaints)": link_acc,
            "noise_rejected": noise_rejected, "severity_spearman": sev_rho}

def main():
    preds = load(get_path("predictions"))
    m = nlp_metrics(preds, load(get_path("labels")))
    print("NLP quality vs hidden labels:")
    for k, v in m.items(): print(f"  {k:40s} {v:.3f}")

if __name__ == "__main__":
    main()
