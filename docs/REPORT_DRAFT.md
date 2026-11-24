# Impact-Aware Query Optimization Prioritization — Draft Report

*Numbers are from the author's full-scale run (Postgres 16 in Docker, full seed, sentence-transformers all-MiniLM-L6-v2, 376 synthetic complaints, α=0.2, 1000 bootstrap resamples). Items marked [CHECK] must be confirmed against `data/fix_ranking.csv` and `data/fix_results.csv` from that run.*

## 1. Problem and motivation
DBAs usually rank slow queries by technical cost (latency, plan cost, flags). That ignores who is affected: an expensive nightly admin report may never be noticed by users, while a cheap-looking checkout query may generate many complaints. We rank *fixes* by combining technical evidence with NLP-derived user impact.

## 2. Method
1. **Diagnostics.** 25 workload queries are run with `EXPLAIN (ANALYZE, BUFFERS)` on PostgreSQL 16; rule-based flags (sequential scan, missing join index, leading-wildcard LIKE, deep OFFSET, estimate mismatch, sort spill) are computed on the real plan. Daily call counts are an *assumed* traffic mix per feature area, not derived from complaints.
2. **NLP (label-free).** Complaints are preprocessed, embedded (sentence-transformers all-MiniLM-L6-v2; TF-IDF + LSA offline fallback), clustered (agglomerative, k by silhouette), and each complaint is linked to a query by a keyword + embedding similarity against a user-facing description of the query. Severity comes from a text lexicon. Labels are never read by this code (enforced by a test).
3. **Impact.** Per query: 0.6·normalised volume + 0.4·normalised severity, scaled by linking confidence.
4. **Fusion.** `score = α·technical + (1−α)·impact` (α=0.2, tuned on a 70/30 hold-out). Variants: reciprocal-rank fusion, *measured* technical gain (real latency saved per day after building the candidate index), and an effort-aware variant (÷ index size and build time).
5. **Fix recommendations.** Candidate indexes are derived from the plans, actually built, and re-measured. Fixes are grouped (one index can serve several queries) and ranked by benefit ÷ effort.

## 3. Evaluation setup
The ideal ranking comes only from the hidden labels (per-query sum of true complaint severities). Metrics: NDCG@10, share of true user pain resolved at k, *budget pain* (pain resolved when fixes are built in ranking order under an effort budget; queries without an effective index fix resolve nothing), Kendall τ. 95% intervals come from 1000 bootstrap resamples of complaints. Baselines: plan cost, mean latency, total time, call frequency, the composite technical score, random.

## 4. Results (α = 0.2)
| Method | NDCG@10 [95% CI] | Budget pain [95% CI] |
|---|---|---|
| Plan cost only | 0.408 [0.338, 0.486] | 0.507 [0.452, 0.561] |
| Mean latency | 0.371 [0.309, 0.432] | 0.512 [0.459, 0.568] |
| Total time | 0.548 [0.477, 0.621] | 0.447 [0.393, 0.500] |
| Call frequency | 0.604 [0.525, 0.678] | 0.561 [0.509, 0.617] |
| Composite technical score | 0.533 [0.459, 0.605] | 0.447 [0.393, 0.500] |
| Random | 0.430 [0.203, 0.676] | 0.478 [0.219, 0.682] |
| **Fused (impact-aware)** | **0.870 [0.767, 0.950]** | **0.627 [0.509, 0.716]** |
| Fused, measured gain | 0.872 [0.775, 0.948] | 0.622 [0.510, 0.716] |
| Fused, RRF | 0.823 [0.705, 0.914] | 0.623 [0.414, 0.689] |
| Fused, effort-aware | 0.848 [0.775, 0.933] | 0.533 [0.429, 0.704] |

Fused beats the composite technical baseline by +0.337 NDCG@10 (95% CI [+0.205, +0.450]), +0.256 in share of user pain resolved at k=10 ([+0.166, +0.336]) and +0.180 in budget pain ([+0.061, +0.288]); in 99–100% of bootstrap resamples fused is better. The effort-aware variant improves NDCG and Kendall τ (0.702 vs 0.319 for the technical score) but its budget-pain gain (+0.086, CI [−0.035, +0.249]) is not statistically significant, so we do not claim it helps under an effort budget.

**NLP quality** (vs hidden labels): link accuracy 0.676, clustering ARI 0.431, purity 0.630, noise complaints rejected 0.70, severity Spearman 0.314. The severity labels are random draws in the generator, so a low correlation is expected.

**α-sweep.** NDCG@10 is flat at about 0.87–0.88 for α between 0.0 and 0.5, then falls to 0.53 (heuristic score) at α=1. Impact-only (α=0) is already 0.870. Hold-out tuning chose α with mean 0.35 (range 0.0–0.6); test NDCG with tuned α is 0.857 versus 0.863 for fixed α=0.2 and 0.515 for technical-only, so tuning does not beat a fixed small α.

**Ablation (NDCG@10).** Technical only 0.532; impact only 0.869; fused 0.879; fused without confidence weighting 0.914; fused with measured gain 0.877; effort-aware 0.853; RRF 0.827.

**Noise robustness.** Randomising 30% of complaint-to-query links lowers fused NDCG@10 only from 0.884 to 0.864 (technical-only: 0.543).

**Case study.** [CHECK] The admin reports (Q16–Q18) are expensive but nearly complaint-free and showed about 1.0× speedup from candidate indexes in `fix_results.csv`; confirm in your run, then state that a cost-only ranking spends effort on them while the impact-aware list ranks them low.

**Top recommended fixes.** [CHECK] Copy the top rows of `data/fix_ranking.csv` (index DDL, queries served, measured speedup) here.

## 5. Limitations (state these honestly)
- Complaints are synthetic and template-based; the 4× scale-up only adds prefix/suffix variation, so duplicates inflate linking accuracy and shrink confidence intervals.
- The ideal ranking is a *user-pain* ranking, so impact-only is almost as good as fused by construction; the technical signal cannot improve NDCG against it. Budget pain partially addresses this by requiring realisable fixes.
- The NDCG curve is flat for α from 0 to 0.5, so we cannot show that the technical signal adds ranking value beyond impact; the technical score is a weak proxy for the benefit of a fix.
- Confidence weighting hurt NDCG (0.879 vs 0.914), probably because linking confidence is weakly calibrated; a floor or calibration is future work.
- Traffic per feature area is assumed. Timing runs are millisecond-scale and noisy, so borderline fixes (≈1.3×) can flip between runs.
- Noise-complaint rejection is 70%, so about a third of off-topic complaints still get linked to a query.

## 6. Future work
Real sentence embeddings; real complaints (app-store or support-ticket data); calibrated linking confidence; learning α and weights; time-trend signals; richer fixes (query rewrites, not only indexes).
