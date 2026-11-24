"""Independent ideal ranking, built ONLY from labels.csv (true links + true severity).
Frozen to data/ideal_ranking.csv; never derived from any model output."""
from __future__ import annotations
import csv, sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.config_loader import get_path

def ideal_scores(label_rows):
    """User-pain per query = sum of true severities of its complaints (= volume × mean severity)."""
    pain = defaultdict(float)
    for r in label_rows:
        if r["true_query_id"] != "NOISE":
            pain[r["true_query_id"]] += int(r["severity_label"])
    return dict(pain)

def main():
    labels = list(csv.DictReader(open(get_path("labels"), encoding="utf-8")))
    with open(get_path("queries"), encoding="utf-8") as f:
        qids = [r["query_id"] for r in csv.DictReader(f)]
    pain = ideal_scores(labels)
    rows = sorted(({"query_id": q, "ideal_pain": pain.get(q, 0.0)} for q in qids), key=lambda r: (-r["ideal_pain"], r["query_id"]))
    for i, r in enumerate(rows, 1): r["ideal_rank"] = i
    out = get_path("data_dir") / "ideal_ranking.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ideal_rank", "query_id", "ideal_pain"]); w.writeheader(); w.writerows(rows)
    print(f"Wrote ideal ranking → {out}")

if __name__ == "__main__":
    main()
