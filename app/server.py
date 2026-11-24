"""Impact-Aware QOP – web application backend (FastAPI).

Run:  python -m uvicorn app.server:app --port 8000      then open http://localhost:8000
"""
from __future__ import annotations
import csv, io, json, re, sqlite3, sys, threading, time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from db.config_loader import load_config, get_path
from fusion.impact import impact_by_query
from fusion.prioritize import load_fix_data, tech_gain, build_fix_ranking
from nlp import run_nlp

APP_DB = ROOT / "app" / "app.db"
STATUSES = ["new", "planned", "applied", "dismissed"]
lock = threading.Lock()

# ------------------------------------------------------------------ storage
def db():
    c = sqlite3.connect(APP_DB); c.row_factory = sqlite3.Row
    return c

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS fix_status (idx TEXT PRIMARY KEY, status TEXT NOT NULL, note TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS live_complaints (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT, created_at TEXT,
            query_id TEXT, confidence REAL, severity INTEGER, source TEXT);
        CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, action TEXT, detail TEXT);
        """)

def audit(action, detail):
    with db() as c:
        c.execute("INSERT INTO audit(ts, action, detail) VALUES (?,?,?)", (datetime.now(timezone.utc).isoformat(timespec="seconds"), action, detail))

def rd(path):
    with open(path, encoding="utf-8") as f: return list(csv.DictReader(f))

# ------------------------------------------------------------------ data layer
class Data:
    """Everything produced by the offline pipeline, plus the NLP linker for live complaints."""
    def load(self):
        d = get_path("data_dir")
        self.queries = {r["query_id"]: r for r in rd(get_path("queries"))}
        self.diag = rd(get_path("diagnostics"))
        self.diag_by = {r["query_id"]: r for r in self.diag}
        self.preds = rd(get_path("predictions"))
        self.complaints = {r["complaint_id"]: r for r in rd(get_path("complaints"))}
        self.fixes, self.effort = load_fix_data()
        self.fix_results = {r["query_id"]: r for r in rd(d / "fix_results.csv")}
        self.index_costs = {r["index"]: r for r in rd(d / "index_costs.csv")}
        ctx = run_nlp.load_queries()
        docs = [run_nlp.preprocess(c["text"]) for c in self.complaints.values()]
        qdocs = [run_nlp.preprocess(q["ui_text"]) for q in ctx.values()]
        cfg = load_config()["nlp"]
        self.docs = docs
        self.emb = run_nlp.Embedder(docs + qdocs, cfg.get("embedding_dim", 30), cfg.get("random_state", 42))
        self.link = run_nlp.build_linker(self.docs, ctx, self.emb)
        self.min_score = cfg["linking"]["min_link_score"]
        self.loaded_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    def link_text(self, text):
        with lock:
            self.docs.append(run_nlp.preprocess(text))
            qid, conf, margin, scores = self.link([len(self.docs) - 1])
        return (qid, conf) if conf >= self.min_score else ("", 0.0)

D = Data()

def all_complaint_rows():
    """pipeline predictions + live complaints, as one list of dicts"""
    rows = []
    for p in D.preds:
        c = D.complaints.get(p["complaint_id"], {})
        rows.append({"id": p["complaint_id"], "text": c.get("text", ""), "created_at": c.get("timestamp", ""), "source": c.get("source", "import"),
                     "query_id": p["pred_query_id"], "confidence": float(p["pred_confidence"]), "severity": int(p["pred_severity"]), "live": False})
    with db() as c:
        for r in c.execute("SELECT * FROM live_complaints ORDER BY id"):
            rows.append({"id": f"L{r['id']:04d}", "text": r["text"], "created_at": r["created_at"], "source": r["source"] or "app",
                         "query_id": r["query_id"], "confidence": r["confidence"], "severity": r["severity"], "live": True})
    return rows

def statuses():
    with db() as c: return {r["idx"]: dict(r) for r in c.execute("SELECT * FROM fix_status")}

def compute(alpha):
    rows = all_complaint_rows()
    impact = impact_by_query((r["query_id"], r["confidence"], r["severity"]) for r in rows)
    counts = defaultdict(int)
    for r in rows:
        if r["query_id"]: counts[r["query_id"]] += 1
    tg, saved = tech_gain(D.diag, D.fixes)
    # fixes
    fx = build_fix_ranking(D.diag, impact, alpha, D.fixes, D.effort, counts)
    st = statuses()
    for f in fx:
        s = st.get(f["index"], {})
        f["status"] = s.get("status", "new"); f["note"] = s.get("note", "")
        qs = f["queries"].split("|")
        f["query_list"] = qs
        f["saved_s_per_day"] = round(sum(saved[q] / len(D.fixes[q]["indexes"]) for q in qs) / 1000, 1)
        f["rollback"] = f"DROP INDEX CONCURRENTLY IF EXISTS {f['index']};"
        f["ddl_concurrent"] = re.sub(r"(?i)^CREATE INDEX ", "CREATE INDEX CONCURRENTLY IF NOT EXISTS ", f["ddl"])
    # queries (fused ranking, plus baseline rank = technical score only)
    tech = {r["query_id"]: float(r["tech_score"]) for r in D.diag}
    fused = {q: alpha * tech[q] + (1 - alpha) * impact.get(q, 0.0) for q in tech}
    order = sorted(fused, key=lambda q: (-fused[q], q)); base = sorted(tech, key=lambda q: (-tech[q], q))
    rank, brank = {q: i for i, q in enumerate(order, 1)}, {q: i for i, q in enumerate(base, 1)}
    fixed_by = defaultdict(list)
    for f in fx:
        for q in f["query_list"]: fixed_by[q].append(f["index"])
    qrows = []
    for q in order:
        d, meta = D.diag_by[q], D.queries[q]
        qrows.append({"query_id": q, "feature_area": meta["feature_area"], "description": meta["description"], "rank": rank[q], "baseline_rank": brank[q],
                      "tech_score": tech[q], "impact": round(impact.get(q, 0.0), 3), "score": round(fused[q], 3), "complaints": counts.get(q, 0),
                      "mean_ms": float(d["mean_ms"]), "calls": int(float(d["calls"])), "flags": [x for x in d["flags"].split("|") if x],
                      "fixes": fixed_by.get(q, []), "fixable": q in D.fixes,
                      "speedup": D.fixes[q]["speedup"] if q in D.fixes else None})
    return {"fixes": fx, "queries": qrows, "impact": impact, "counts": counts, "complaints": rows, "saved": saved}

# ------------------------------------------------------------------ app
app = FastAPI(title="Impact-Aware QOP")

@app.on_event("startup")
def _startup():
    init_db(); D.load()

class StatusBody(BaseModel):
    status: str
    note: str = ""

class ComplaintBody(BaseModel):
    text: str
    source: str = "app"

class ConfirmBody(BaseModel):
    confirm: bool = False

@app.get("/api/summary")
def summary(alpha: float = Query(None, ge=0, le=1)):
    alpha = load_config()["fusion"]["alpha"] if alpha is None else alpha
    s = compute(alpha)
    linked = [c for c in s["complaints"] if c["query_id"]]
    open_fixes = [f for f in s["fixes"] if f["status"] in ("new", "planned")]
    covered = sum(1 for c in linked if c["query_id"] in D.fixes)
    return {"alpha": alpha, "loaded_at": D.loaded_at, "backend": D.emb.backend,
            "kpis": {"open_fixes": len(open_fixes), "applied_fixes": sum(1 for f in s["fixes"] if f["status"] == "applied"),
                     "complaints": len(s["complaints"]), "linked": len(linked),
                     "covered_pct": round(100 * covered / len(linked)) if linked else 0,
                     "saved_s_per_day": round(sum(f["saved_s_per_day"] for f in open_fixes)),
                     "top_fix": open_fixes[0]["ddl"] if open_fixes else None},
            "unfixable": [q["query_id"] for q in s["queries"] if not q["fixable"] and q["complaints"] == 0 and "admin" in q["feature_area"]]}

@app.get("/api/fixes")
def fixes(alpha: float = Query(None, ge=0, le=1)):
    alpha = load_config()["fusion"]["alpha"] if alpha is None else alpha
    return compute(alpha)["fixes"]

@app.get("/api/queries")
def queries(alpha: float = Query(None, ge=0, le=1)):
    alpha = load_config()["fusion"]["alpha"] if alpha is None else alpha
    return compute(alpha)["queries"]

@app.get("/api/queries/{qid}")
def query_detail(qid: str, alpha: float = Query(None, ge=0, le=1)):
    if qid not in D.queries: raise HTTPException(404, "unknown query")
    alpha = load_config()["fusion"]["alpha"] if alpha is None else alpha
    s = compute(alpha); q = next(x for x in s["queries"] if x["query_id"] == qid)
    plan = None
    try: plan = json.loads(D.diag_by[qid]["plan_json"]) if D.diag_by[qid]["plan_json"] else None
    except Exception: pass
    fr = D.fix_results.get(qid)
    return {**q, "sql": D.queries[qid]["sql_text"], "plan": plan, "measured": fr,
            "complaint_examples": [c for c in s["complaints"] if c["query_id"] == qid][:12]}

@app.get("/api/complaints")
def complaints(query_id: str = "", q: str = "", limit: int = 200):
    rows = all_complaint_rows()
    if query_id == "unlinked": rows = [r for r in rows if not r["query_id"]]
    elif query_id: rows = [r for r in rows if r["query_id"] == query_id]
    if q: rows = [r for r in rows if q.lower() in r["text"].lower()]
    rows.sort(key=lambda r: (not r["live"], r["created_at"]), reverse=False)
    rows = sorted(rows, key=lambda r: r["created_at"], reverse=True)
    return {"total": len(rows), "items": rows[:limit]}

@app.post("/api/complaints")
def add_complaint(body: ComplaintBody):
    text = body.text.strip()
    if len(text) < 5: raise HTTPException(400, "Complaint text is too short")
    if len(text) > 1000: raise HTTPException(400, "Complaint text is too long")
    qid, conf = D.link_text(text); sev = run_nlp.severity(text)
    with db() as c:
        cur = c.execute("INSERT INTO live_complaints(text, created_at, query_id, confidence, severity, source) VALUES (?,?,?,?,?,?)",
                        (text, datetime.now(timezone.utc).isoformat(timespec="seconds"), qid, conf, sev, body.source[:40]))
        cid = cur.lastrowid
    audit("complaint", f"L{cid:04d} linked to {qid or 'nothing'} (confidence {conf:.2f}, severity {sev})")
    q = D.queries.get(qid)
    return {"id": f"L{cid:04d}", "query_id": qid, "confidence": round(conf, 3), "severity": sev,
            "query_description": q["description"] if q else None}

@app.post("/api/fixes/{index}/status")
def set_status(index: str, body: StatusBody):
    if index not in D.index_costs: raise HTTPException(404, "unknown fix")
    if body.status not in STATUSES: raise HTTPException(400, f"status must be one of {STATUSES}")
    with db() as c:
        c.execute("INSERT INTO fix_status(idx,status,note,updated_at) VALUES (?,?,?,?) ON CONFLICT(idx) DO UPDATE SET status=excluded.status, note=excluded.note, updated_at=excluded.updated_at",
                  (index, body.status, body.note[:500], datetime.now(timezone.utc).isoformat(timespec="seconds")))
    audit("status", f"{index} → {body.status}" + (f" ({body.note[:80]})" if body.note else ""))
    return {"ok": True}

def run_sql(*statements):
    """Run statements on an autocommit connection. (psycopg2 >= 2.9: `with conn:` would open a transaction,
    which CREATE/DROP INDEX CONCURRENTLY refuse.)"""
    conn = pg()
    try:
        cur = conn.cursor()
        for st in statements: cur.execute(st)
    finally:
        conn.close()

def pg():
    import psycopg2
    c = psycopg2.connect(load_config()["database"]["url"], connect_timeout=4); c.autocommit = True
    return c

@app.get("/api/db/health")
def db_health():
    try:
        with pg() as c, c.cursor() as cur:
            cur.execute("SELECT version()"); return {"ok": True, "version": cur.fetchone()[0].split(",")[0]}
    except Exception as e:
        return {"ok": False, "error": str(e).strip().splitlines()[0][:160]}

@app.post("/api/fixes/{index}/apply")
def apply_fix(index: str, body: ConfirmBody):
    if not body.confirm: raise HTTPException(400, "Confirmation required")
    f = next((x for x in compute(0.2)["fixes"] if x["index"] == index), None)
    if not f: raise HTTPException(404, "unknown fix")
    try:
        t0 = time.time()
        run_sql(f["ddl_concurrent"], "ANALYZE")
        secs = round(time.time() - t0, 2)
    except Exception as e:
        audit("apply-failed", f"{index}: {str(e).strip().splitlines()[0][:120]}")
        raise HTTPException(500, f"Could not apply: {str(e).strip().splitlines()[0][:200]}")
    with db() as c:
        c.execute("INSERT INTO fix_status(idx,status,note,updated_at) VALUES (?,?,?,?) ON CONFLICT(idx) DO UPDATE SET status='applied', updated_at=excluded.updated_at",
                  (index, "applied", "applied from the app", datetime.now(timezone.utc).isoformat(timespec="seconds")))
    audit("apply", f"{index} created concurrently in {secs}s")
    return {"ok": True, "seconds": secs}

@app.post("/api/fixes/{index}/rollback")
def rollback_fix(index: str, body: ConfirmBody):
    if not body.confirm: raise HTTPException(400, "Confirmation required")
    if index not in D.index_costs: raise HTTPException(404, "unknown fix")
    try:
        run_sql(f"DROP INDEX CONCURRENTLY IF EXISTS {index}")
    except Exception as e:
        raise HTTPException(500, f"Could not roll back: {str(e).strip().splitlines()[0][:200]}")
    with db() as c:
        c.execute("INSERT INTO fix_status(idx,status,note,updated_at) VALUES (?,?,?,?) ON CONFLICT(idx) DO UPDATE SET status='planned', updated_at=excluded.updated_at",
                  (index, "planned", "rolled back", datetime.now(timezone.utc).isoformat(timespec="seconds")))
    audit("rollback", f"{index} dropped")
    return {"ok": True}

@app.post("/api/fixes/{index}/verify")
def verify_fix(index: str):
    """Re-run EXPLAIN ANALYZE of every query the fix serves and compare with the pre-fix measurement."""
    from diagnostics.live import explain
    f = next((x for x in compute(0.2)["fixes"] if x["index"] == index), None)
    if not f: raise HTTPException(404, "unknown fix")
    out = []
    try:
        with pg() as c, c.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_indexes WHERE indexname=%s", (index,))
            exists = cur.fetchone() is not None
            for q in f["query_list"]:
                ms, _ = explain(cur, D.queries[q]["sql_text"], 3)
                before = D.fixes[q]["before"]
                out.append({"query_id": q, "before_ms": before, "now_ms": round(ms, 3), "speedup": round(before / ms, 1) if ms else None})
    except Exception as e:
        raise HTTPException(500, f"Database not reachable: {str(e).strip().splitlines()[0][:200]}")
    audit("verify", f"{index} (index present: {exists})")
    return {"index_present": exists, "results": out}

@app.get("/api/evaluation")
def evaluation():
    r = ROOT / "eval" / "results"
    def maybe(name):
        p = r / name
        return rd(p) if p.exists() else []
    return {"metrics": maybe("metrics.csv"), "ablation": maybe("ablation.csv"), "alpha_sweep": maybe("alpha_sweep.csv"),
            "noise": maybe("noise_robustness.csv"), "images": [n for n in ("complaints_resolved_curve.png", "alpha_sweep.png", "noise_robustness.png") if (r / n).exists()]}

@app.get("/api/audit")
def audit_log(limit: int = 100):
    with db() as c: return [dict(r) for r in c.execute("SELECT ts, action, detail FROM audit ORDER BY id DESC LIMIT ?", (limit,))]

@app.get("/api/export/fixes.csv")
def export_csv(alpha: float = 0.2):
    f = compute(alpha)["fixes"]; buf = io.StringIO()
    w = csv.writer(buf); w.writerow(["rank", "status", "ddl", "queries", "complaints", "best_speedup", "index_mb", "priority", "note"])
    for x in f: w.writerow([x["rank"], x["status"], x["ddl"], x["queries"], x["complaints"], x["best_speedup"], x["index_mb"], x["priority"], x["note"]])
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=fix_priorities.csv"})

@app.get("/api/export/report.md")
def export_md(alpha: float = 0.2):
    s = compute(alpha); lines = [f"# Query fix priorities ({datetime.now():%Y-%m-%d})", "", f"Weighting α = {alpha} (technical) / {1-alpha:.1f} (user impact)", ""]
    for f in s["fixes"]:
        lines += [f"## {f['rank']}. {f['ddl']}", f"- Status: {f['status']}", f"- Serves: {', '.join(f['query_list'])} · {f['complaints']} linked complaints · measured speedup up to ×{f['best_speedup']:.0f}",
                  f"- Index size: {f['index_mb']} MB", f"- Rollback: `{f['rollback']}`", ""]
    return PlainTextResponse("\n".join(lines), headers={"Content-Disposition": "attachment; filename=fix_priorities.md"})

@app.post("/api/reload")
def reload_data():
    D.load(); audit("reload", "pipeline outputs re-read from disk"); return {"ok": True, "loaded_at": D.loaded_at}

app.mount("/results", StaticFiles(directory=ROOT / "eval" / "results"), name="results")
app.mount("/static", StaticFiles(directory=ROOT / "app" / "static"), name="static")

@app.get("/")
def index():
    return FileResponse(ROOT / "app" / "static" / "index.html")
