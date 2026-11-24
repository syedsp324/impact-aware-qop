"""Phase 6 – Minimal Streamlit demo."""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"

st.set_page_config(page_title="Impact-Aware QOP", layout="wide")
st.title("Impact-Aware Query Optimization Prioritization")
st.caption("Fusing NLP user feedback with database diagnostics")

def load(name):
    path = DATA / name
    if not path.exists():
        st.warning(f"Missing {name}. Run: make diagnose cluster rank")
        return pd.DataFrame()
    return pd.read_csv(path)

page = st.sidebar.radio("Navigate", [
    "Fix Recommendations", "Priority List (Fused)", "Baseline vs Fused", "Experiments", "Complaints & Clusters", "Query Diagnostics"])

if page == "Fix Recommendations":
    st.header("Recommended index fixes (benefit ÷ effort)")
    fx = load("fix_ranking.csv")
    if not fx.empty:
        st.dataframe(fx[["rank","ddl","queries","complaints","best_speedup","index_mb","priority"]], use_container_width=True, hide_index=True)
        top = fx.iloc[0]
        st.subheader("Top recommendation")
        st.code(top["ddl"], language="sql")
        st.markdown(top["reasoning"])
        fr = load("fix_results.csv")
        if not fr.empty:
            st.subheader("Measured before/after latency per query")
            st.dataframe(fr[["query_id","before_ms","after_ms","speedup","accepted","ddl"]], use_container_width=True, hide_index=True)

elif page == "Priority List (Fused)":
    st.header("Impact-Aware Priority List")
    fused = load("ranking_fused.csv")
    if not fused.empty:
        alpha = st.slider("α (technical weight)", 0.0, 1.0, 0.2, 0.1)
        fused = fused.copy()
        fused["fused_score"] = alpha*fused["tech_score"] + (1-alpha)*fused["impact_score"]
        fused = fused.sort_values("fused_score", ascending=False).reset_index(drop=True)
        fused["rank"] = range(1, len(fused)+1)
        st.dataframe(fused[["rank","query_id","tech_score","impact_score","fused_score",
                            "complaint_count","flags","suggested_fix"]].head(15),
                     use_container_width=True, hide_index=True)
        top = fused.iloc[0]
        st.subheader("Top recommendation")
        st.markdown(f"**{top['query_id']}** — {top.get('reasoning','')}")
        st.code(top.get("suggested_fix",""), language="sql")

elif page == "Baseline vs Fused":
    st.header("Baseline vs Fused")
    base = load("ranking_baseline.csv")
    fused = load("ranking_fused.csv")
    if not base.empty and not fused.empty:
        base_r = base.set_index("query_id")["rank"].to_dict()
        fused["base_rank"] = fused["query_id"].map(base_r)
        fused["delta"] = fused["base_rank"] - fused["rank"]
        st.dataframe(fused[["rank","base_rank","delta","query_id","complaint_count",
                            "tech_score","impact_score","flags"]].head(15),
                     use_container_width=True, hide_index=True)
        curve = ROOT / "eval/results/complaints_resolved_curve.png"
        if curve.exists():
            st.image(str(curve), caption="Complaints resolved @k")

elif page == "Experiments":
    st.header("Experiments")
    for img, cap in (("complaints_resolved_curve.png", "Share of true user pain resolved vs top-k fixes"),
                     ("alpha_sweep.png", "α-sweep with 95% CI"), ("noise_robustness.png", "Robustness to wrong complaint links")):
        p = ROOT / "eval/results" / img
        if p.exists(): st.image(str(p), caption=cap)
    for name in ("metrics.csv", "ablation.csv"):
        p = ROOT / "eval/results" / name
        if p.exists():
            st.subheader(name); st.dataframe(pd.read_csv(p), use_container_width=True, hide_index=True)

elif page == "Complaints & Clusters":
    st.header("Complaints & Clusters")
    comps = load("complaints.csv")
    clusters = load("clusters.csv")
    if not comps.empty:
        st.dataframe(comps[["complaint_id","text","source"]].head(20),
                     use_container_width=True, hide_index=True)
    if not clusters.empty:
        st.dataframe(clusters.sort_values("impact_score", ascending=False),
                     use_container_width=True, hide_index=True)

elif page == "Query Diagnostics":
    st.header("Technical Diagnostics")
    diag = load("diagnostics.csv")
    queries = load("queries.csv")
    if not diag.empty:
        merged = diag.merge(queries[["query_id","feature_area","description"]], on="query_id", how="left")
        st.dataframe(merged[["query_id","feature_area","mean_ms","calls","tech_score","flags","description"]]
                     .sort_values("tech_score", ascending=False),
                     use_container_width=True, hide_index=True)

st.sidebar.markdown("---")
for f in ["queries.csv","diagnostics.csv","fix_results.csv","complaints.csv","clusters.csv",
          "ranking_baseline.csv","ranking_fused.csv","fix_ranking.csv"]:
    st.sidebar.write(f"{'✅' if (DATA/f).exists() else '❌'} {f}")
