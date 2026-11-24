# Impact-Aware Query Optimization Prioritization

Fusing NLP-driven user feedback with database query diagnostics for prioritized fix recommendation.

## Quick Start (offline pipeline – no Postgres required)

```bash
cd impact-aware-qop
python3 -m diagnostics.run_diagnostics   # queries + technical scores
python3 -m nlp.complaints_data           # 94 complaints
python3 -m nlp.run_nlp                   # clusters + linking + impact
python3 -m fusion.run_fusion             # baseline + fused rankings
python3 -m eval.run_evaluation           # metrics + figure
# streamlit run dashboard/app.py         # demo (if streamlit installed)
```

Or: `make pipeline`

## With live Postgres

```bash
make up          # start Postgres 16 + pg_stat_statements
make seed        # load 100k–1.5M row e-commerce data
make diagnose    # real EXPLAIN ANALYZE (falls back to synthetic if DB down)
```

## Project Structure

```
db/            schema + seed
diagnostics/   workload, rules, plan parser, tech scores
nlp/           complaints, clustering, linking
fusion/        baseline + impact-aware rankers
eval/          metrics + plots
dashboard/     Streamlit demo
data/          all CSV contracts
docs/          contracts, status
```

## Web app

```
python -m app          # opens http://localhost:8000
```

Pages: **Priorities** (ranked index fixes with benefit/effort, α slider, status workflow, apply / verify / roll back on the database),
**Queries** (rank movement vs a cost-only ranking, plans, measured speedups), **Complaints** (live intake: new complaints are linked to a
query and severity-rated immediately, and the ranking updates), **Evaluation** (metrics with confidence intervals, α-sweep, ablation),
**Activity** (audit log). Exports: CSV and Markdown report. State (statuses, new complaints, audit log) lives in `app/app.db` (SQLite).
It reads the pipeline output in `data/`, so run the pipeline first. "Apply fix" runs `CREATE INDEX CONCURRENTLY` on the configured database.

## Status

- [x] Phases 0-6 (setup, schema, diagnostics, NLP, fusion, evaluation, dashboard)
- [x] Label-free NLP (TF-IDF/LSA; sentence-transformers used automatically if installed)
- [x] Independent evaluation: ideal ranking from hidden labels, 6 baselines, NDCG / Kendall / budget metrics, bootstrap CIs
- [x] Live Postgres diagnostics, measured index fixes, fix-grouped effort-aware ranking
- [x] Experiments: α-sweep, ablation, noise robustness, hold-out α tuning
- [x] Tests (`make test`), report draft in `docs/REPORT_DRAFT.md`
- [ ] Real sentence-transformers embeddings (pip install, then re-run `make pipeline`)
- [ ] Full-scale seed (`make up && make seed`, default scale) and re-run `make fixes pipeline`
- [ ] Real or externally generated complaints; real traffic mix in `config.yaml` -> `workload`
- [ ] Final report: update the numbers in docs/REPORT_DRAFT.md after the re-run

See PROGRESS.md for the resume log.
