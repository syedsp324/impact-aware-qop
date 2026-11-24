"""Phase 3 – NLP: preprocess → embed → cluster → link → severity → impact.

This module NEVER reads labels.csv / true_query_id. Labels are only used by
eval/nlp_eval.py to score what this module produced.
"""
from __future__ import annotations
import csv, re, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer, ENGLISH_STOP_WORDS
from sklearn.decomposition import TruncatedSVD
from sklearn.cluster import KMeans, AgglomerativeClustering
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import normalize

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db.config_loader import load_config, get_path

KEEP = {"not", "no", "never", "cannot"}
STOP = set(ENGLISH_STOP_WORDS) - KEEP | {"app", "page", "slow", "forever", "ages", "take", "takes", "taking",
                                         "loading", "load", "loads", "long", "time", "bad", "super", "very"}
# NOTE: generic "slowness" words are removed for topic grouping: every complaint
# says them, so they carry no information about WHICH feature is slow.

def stem(w: str) -> str:
    for suf in ("ing", "ies", "es", "ed", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w

def preprocess(text: str) -> str:
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return " ".join(stem(w) for w in text.split() if w not in STOP and len(w) > 1)

# ---------- IO (public columns only) ----------
def load_complaints():
    with open(get_path("complaints"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert "true_query_id" not in rows[0], "complaints.csv must not contain labels"
    return rows

def load_queries():
    with open(get_path("queries"), encoding="utf-8") as f:
        q = {r["query_id"]: r for r in csv.DictReader(f)}
    with open(get_path("query_context"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["query_id"] in q:
                q[r["query_id"]]["ui_text"] = r["ui_text"]
    return q

# ---------- Embedding ----------
class Embedder:
    """sentence-transformers if installed, else TF-IDF + LSA (offline fallback)."""
    def __init__(self, texts_for_fit, dim=30, seed=42):
        self.backend = "lsa"
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(load_config()["nlp"]["embedding_model"])
            self.backend = "sbert"
        except Exception:
            self.tfidf = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1).fit(texts_for_fit)
            n = self.tfidf.transform(texts_for_fit).shape
            self.svd = TruncatedSVD(n_components=min(dim, min(n) - 1), random_state=seed).fit(self.tfidf.transform(texts_for_fit))
    def encode(self, texts):
        if self.backend == "sbert":
            return normalize(self.model.encode(list(texts)))
        return normalize(self.svd.transform(self.tfidf.transform(texts)))

# ---------- Clustering ----------
def cluster(X, min_k, max_k, seed):
    """Agglomerative (cosine, average) on TF-IDF vectors; k chosen by silhouette."""
    best = (-1, None, None)
    for k in range(min_k, min(max_k, len(X) - 1) + 1):
        labels = AgglomerativeClustering(n_clusters=k, metric="cosine", linkage="average").fit_predict(X)
        if len(set(labels)) < 2:
            continue
        s = silhouette_score(X, labels, metric="cosine")
        if s > best[0]:
            best = (s, k, labels)
    return best  # silhouette, k, labels

# ---------- Linking ----------
def build_linker(complaint_docs, queries, emb):
    """Returns f(list_of_doc_indices) -> (best_qid, confidence, score_by_qid)."""
    cfg = load_config()["nlp"]["linking"]
    qids = sorted(queries)
    qdocs = [preprocess(queries[q]["ui_text"] + " " + queries[q]["feature_area"].replace("_", " ")) for q in qids]
    kw = TfidfVectorizer(sublinear_tf=True).fit(complaint_docs + qdocs)
    Q_kw = kw.transform(qdocs)
    Q_emb = emb.encode(qdocs)
    def link(idx):
        c_kw = kw.transform([" ".join(complaint_docs[i] for i in idx)])
        kw_s = (c_kw @ Q_kw.T).toarray()[0]
        e = normalize(emb.encode([complaint_docs[i] for i in idx]).mean(axis=0, keepdims=True))
        em_s = (e @ Q_emb.T)[0]
        score = cfg["keyword_weight"] * kw_s + cfg["embedding_weight"] * np.clip(em_s, 0, None)
        order = np.argsort(-score)
        best, second = score[order[0]], score[order[1]]
        conf = float(best) if best > 0 else 0.0
        margin = float((best - second) / best) if best > 0 else 0.0
        return qids[order[0]], conf, margin, {q: float(s) for q, s in zip(qids, score)}
    return link

# ---------- Severity (text only) ----------
SEV3 = ["unusable", "lost", "broken", "timeout", "timed out", "never", "can t", "cannot", "ridiculous", "useless", "die",
        "freez", "hang", "stuck", "fail", "wrong", "refund", "minute", "second", "waited", "sale"]
SEV2 = ["slow", "lag", "spinn", "forever", "ages", "long", "delay", "unresponsive", "empty", "blank", "painful"]
def severity(text: str) -> int:
    t = text.lower().replace("'", " ")
    s3 = sum(w in t for w in SEV3) + (t.count("!") >= 1) + (t.count("?") >= 2)
    s2 = sum(w in t for w in SEV2)
    return 3 if s3 >= 2 else 2 if (s3 == 1 or s2 >= 1) else 1

# ---------- Impact ----------
def compute_impact_scores(clusters):
    cfg = load_config()["fusion"]
    def norm(v, lo, hi): return 0.5 if hi == lo else (v - lo) / (hi - lo)
    vols = [c["volume"] for c in clusters]; sevs = [c["mean_severity"] for c in clusters]
    for c in clusters:
        raw = cfg["volume_weight"] * norm(c["volume"], min(vols), max(vols)) + \
              cfg["severity_weight"] * norm(c["mean_severity"], min(sevs), max(sevs))
        c["impact_score"] = round(raw * c["confidence_weight"], 4)
    return clusters

def write_clusters_csv(clusters, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["cluster_id", "complaint_ids", "linked_query_id", "confidence", "volume", "mean_severity", "impact_score"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(clusters)
    print(f"Wrote {len(clusters)} clusters → {path}")

def write_predictions(complaints, labels, sev, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["complaint_id", "topic_cluster", "pred_query_id", "pred_severity", "pred_confidence"])
        for c, lab, s in zip(complaints, labels, sev):
            w.writerow([c["complaint_id"], run.sem_labels[complaints.index(c)], lab["linked_query_id"], s, run.own_conf[complaints.index(c)]])

def run(min_k=None, max_k=None):
    cfg = load_config()["nlp"]
    complaints, queries = load_complaints(), load_queries()
    docs = [preprocess(c["text"]) for c in complaints]
    qdocs = [preprocess(q["ui_text"]) for q in queries.values()]
    emb = Embedder(docs + qdocs, cfg.get("embedding_dim", 30), cfg.get("random_state", 42))
    X = emb.encode(docs)
    tf = TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2)).fit(docs)
    Xs = normalize(tf.transform(docs)).toarray()
    sil, k, labels = cluster(Xs, min_k or cfg["min_k"], max_k or cfg["max_k"], cfg.get("random_state", 42))
    link = build_linker(docs, queries, emb)
    sev = [severity(c["text"]) for c in complaints]
    min_score = cfg["linking"]["min_link_score"]
    # 1) link every complaint on its own (short texts → cluster centroids blur topics)
    own = [link([i]) for i in range(len(complaints))]
    own_q = [(o[0] if o[1] >= min_score else "") for o in own]
    own_c = [o[1] if o[1] >= min_score else 0.0 for o in own]
    # 2) topic clusters (labels) are kept for exploration/ARI; the groups used for
    #    ranking are the complaints sharing the same linked query (complaint-level link
    #    beat cluster-vote linking: ~65% vs ~44% on this data).
    sem = {i: f"T{int(labels[i])+1:02d}" for i in range(len(complaints))}
    groups = defaultdict(list)
    for i, q in enumerate(own_q):
        if q: groups[q].append(i)
    clusters, per_complaint = [], [None] * len(complaints)
    for n, (qid, idx) in enumerate(sorted(groups.items(), key=lambda kv: -len(kv[1])), 1):
        mean_c = sum(own_c[i] for i in idx) / len(idx)
        cl = {"cluster_id": f"CL{n:02d}", "complaint_ids": "|".join(complaints[i]["complaint_id"] for i in idx),
              "linked_query_id": qid, "confidence": round(mean_c, 3), "volume": len(idx),
              "mean_severity": round(sum(sev[i] for i in idx) / len(idx), 2),
              "confidence_weight": min(1.0, mean_c / 0.5)}
        clusters.append(cl)
        for i in idx: per_complaint[i] = cl
    for i in range(len(complaints)):
        if per_complaint[i] is None:
            per_complaint[i] = {"cluster_id": "", "linked_query_id": ""}
    run.sem_labels = sem
    run.own_conf = [round(x, 4) for x in own_c]
    compute_impact_scores(clusters)
    return complaints, clusters, per_complaint, sev, sil, k, emb.backend

def main():
    print("=" * 60 + "\nImpact-Aware QOP – NLP Pipeline (label-free)\n" + "=" * 60)
    complaints, clusters, per_c, sev, sil, k, backend = run()
    print(f"embedding backend={backend}  chosen k={k}  silhouette={sil:.3f}")
    clusters.sort(key=lambda c: c["impact_score"], reverse=True)
    for c in clusters[:12]:
        print(f"  {c['cluster_id']}  vol={c['volume']:2d}  sev={c['mean_severity']:.1f}  impact={c['impact_score']:.3f}"
              f"  → {c['linked_query_id'] or '—'}  (conf={c['confidence']:.2f})")
    write_clusters_csv(clusters, get_path("clusters"))
    write_predictions(complaints, per_c, sev, get_path("predictions"))
    print("Done. Score it with: python3 -m eval.nlp_eval")

if __name__ == "__main__":
    main()
