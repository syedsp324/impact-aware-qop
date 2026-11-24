# Shared Data Contracts

| File | Key columns | Written by | Read by |
|------|-------------|------------|---------|
| queries.csv | query_id, sql_text, feature_area, description, is_inefficient, impact_group | A | B, C |
| diagnostics.csv | query_id, mean_ms, calls, total_time_ms, plan_cost, flags, flag_count, tech_score | A | C |
| complaints.csv | complaint_id, text, timestamp, severity_label, true_query_id, source | B | B, C |
| ground_truth.csv | complaint_id, query_id, ideal_fix, ideal_rank | A+B | C |
| clusters.csv | cluster_id, complaint_ids, linked_query_id, confidence, volume, mean_severity, impact_score | B | C |
| ranking_baseline.csv / ranking_fused.csv | rank, query_id, tech_score, impact_score, fused_score, flags, suggested_fix, complaint_count, reasoning | C | eval, dashboard |
