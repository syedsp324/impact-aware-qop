# PROGRESS (resume file – read this first in any new session)

Plan doc: https://claude.ai/artifact/19kKWswYtyHb9NQA5Usesj  (Steps 1-6)
Run order: `python3 -m diagnostics.run_diagnostics; python3 -m nlp.complaints_data; python3 -m nlp.run_nlp; python3 -m eval.nlp_eval; python3 -m eval.ground_truth; python3 -m fusion.run_fusion; python3 -m eval.run_evaluation`

## DONE (also see git log)
- [x] Step 1 Real NLP (English only, Hinglish removed). `nlp/run_nlp.py` never reads labels. Labels live in `data/labels.csv`
      (answer key, evaluation only). TF-IDF+LSA embedder (sentence-transformers used automatically if installed – not
      installable in sandbox). Agglomerative topic clusters (k by silhouette) + per-complaint linking to `nlp/query_context.csv`
      (UI-facing text per query). Result: link accuracy 0.655, ARI 0.36, purity 0.61, noise rejected 0.5, severity rho 0.24
      (severity labels in the generator are random draws, so low rho is expected).
- [x] Step 2 Independent evaluation: `eval/ground_truth.py` (ideal pain = sum of true severities), baselines (cost, mean
      latency, total time, calls, composite tech, random), metrics (NDCG@10, P@10, pain resolved@10, Kendall, Spearman),
      bootstrap 95% CIs (1000). Shared impact formula in `fusion/impact.py`.
      Result (alpha=0.5): fused NDCG 0.898 vs composite tech 0.792 (diff +0.106, CI [-0.07,+0.26], P=0.90) – not yet significant.
      FINDING: total_time (0.839) and call_freq (0.867) baselines are strong because synthetic diagnostics set `calls`
      by `impact_group` (leak). Step 3 must remove that.

- [x] Step 3 Real diagnostics: sandbox runs local Postgres 16 (start: see "Sandbox Postgres" below). `diagnostics/live.py` real EXPLAIN
      (ANALYZE,BUFFERS), rules on real plans, `calls` from ASSUMED traffic mix in config `workload.calls_per_day` (not from impact labels).
      Synthetic fallback no longer keyed on impact_group. `diagnostics/measure_fixes.py` derives indexes from plans, builds them, re-measures
      -> data/fix_results.csv, data/index_costs.csv. 10 of 20 candidate fixes effective (>=1.3x); admin report queries NOT fixable by index.
      Data seeded at scale 0.2 (QOP_SEED_SCALE) in the sandbox; full scale is the default on user's machine.
- [x] Step 4 `fusion/prioritize.py`: measured TechGain, effort (index MB + build s), RRF, fix-grouped ranking -> data/fix_ranking.csv.
      Eval metrics added: budget_pain. Results (alpha=.5): fused NDCG .716 vs tech .477 (diff +.239 CI [+.08,+.40]); fused_measured .744;
      fused_effort .795 but budget_pain not better than fused (CI wide).

- [x] Step 5 eval/experiments.py (alpha sweep, ablation, noise, hold-out); complaints scaled 4x (config complaints.scale); alpha set to 0.2.
- [x] Step 6 25 tests pass (make test); dashboard updated (not run: streamlit missing in sandbox, py_compile ok); Makefile pipeline;
      README status; docs/REPORT_DRAFT.md.

## Sandbox Postgres (if container was reset)
`su postgres -c "/usr/lib/postgresql/16/bin/pg_ctl -D /home/claude/pgdata -l /home/claude/pgdata/log -o '-p 5432' -w start"`
If /home/claude/pgdata is gone: initdb it (trust auth), create role qop_user SUPERUSER pw qop_pass + db ecommerce, `QOP_SEED_SCALE=0.2 python3 -m db.seed`.

## REMAINING (needs the user)
See README "Status" unchecked items: sentence-transformers, full-scale seed on user's machine, real complaints, real traffic mix, final numbers.
