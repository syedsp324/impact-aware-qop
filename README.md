# Impact-Aware Query Optimization Prioritization

**Rank which slow database queries a DBA should fix first — using real PostgreSQL plans + user complaint impact (SQL · NoSQL · NLP)**

---

## Why this project exists

Traditional database advisors rank slow queries by **technical cost alone** (latency, plan cost, sequential scans). That can be misleading:

- A nightly admin report may look expensive but affect zero customers  
- A checkout query that looks cheap can generate dozens of user complaints  

This project ranks **fixes**, not just queries, by combining three signals:

1. **Technical severity** — from real `EXPLAIN (ANALYZE)` plans  
2. **User impact** — from NLP analysis of free-text complaints  
3. **Benefit ÷ effort** — measured speedup of candidate indexes versus build cost  

**Aim:** replace *“fix the most expensive query”* with *“fix what hurts users most per unit of effort”*.

---

## Headline result

| Method                   | NDCG@10   |
|--------------------------|-----------|
| Plan cost only           | 0.408     |
| Technical score only     | 0.533     |
| **Impact-aware (fused)** | **0.870** |

Gain over technical baseline: **+0.337** (95% CI [+0.205, +0.450]) on a full-scale run with 376 complaints.

---

## Features

- Real PostgreSQL 16 diagnostics (`EXPLAIN ANALYZE`, `pg_stat_statements`, `pg_trgm`)
- Rule-based detection of seq scans, missing join indexes, leading-wildcard `LIKE`, deep `OFFSET`, etc.
- NLP pipeline: embedding / clustering / linking of user complaints to queries
- Fusion ranking: `score = α·T + (1−α)·I` (default α = 0.2)
- Actual index build → re-time → measure speedup → rank by benefit/effort
- Web app to **review, apply, verify, and roll back** indexes
- MongoDB (NoSQL) store for complaints with text search and aggregation demos
- Evaluation: NDCG@10, budget pain, bootstrap confidence intervals
- 8-table normalized e-commerce schema (~3M rows at full scale)

---

## Architecture (high level)
PostgreSQL (e-commerce data + plans)
│
▼
┌──────────────────┐ ┌─────────────────────┐
│ Diagnostics │ │ User Complaints │
│ EXPLAIN ANALYZE │ │ (CSV + MongoDB) │
│ tech scores │ │ NLP → impact │
└────────┬─────────┘ └──────────┬──────────┘
│ │
└──────────┬───────────────┘
▼
Fusion & Fix Ranking
(benefit ÷ effort)
│
┌──────────┴──────────┐
▼ ▼
Web Application Evaluation
Apply / Verify NDCG, curves
Roll back

Text

---

## Tech stack

| Layer          | Technology |
|----------------|------------|
| SQL database   | PostgreSQL 16 + `pg_stat_statements` + `pg_trgm` |
| NoSQL database | MongoDB 7 (complaints & demo queries) |
| Language       | Python 3.10+ |
| Web backend    | FastAPI + Uvicorn |
| Web frontend   | HTML / CSS / JS (no framework) |
| NLP            | sentence-transformers / scikit-learn (TF-IDF+LSA fallback) |
| Containers     | Docker Compose |
| App state      | SQLite (`app/app.db`) |

---

## Project structure
impact-aware-qop/
├── app/ # FastAPI web application
├── db/ # Schema + seed script
├── diagnostics/ # Workload, EXPLAIN, rules, fix measurement
├── nlp/ # Complaints, clustering, linking, impact
├── fusion/ # Baseline + impact-aware ranking
├── eval/ # NDCG, experiments, plots
├── nosql/ # MongoDB seed + demo queries
├── data/ # Pipeline CSV contracts (generated)
├── docs/ # Contracts, report drafts
├── tests/ # Automated tests
├── docker-compose.yml # PostgreSQL + MongoDB
├── config.yaml # Paths, weights, DB settings
├── Makefile
└── requirements.txt

Text

---

## Two kinds of queries (important)

### 1. Workload SQL queries (what we prioritise)

These are the **25 application queries** (order history, product search, checkout, …) that run against the e-commerce schema. Some are deliberately inefficient. The system decides **which of these to fix first**.

- Source: `diagnostics/workload.py`  
- Export: `data/queries.csv`

### 2. NoSQL (MongoDB) queries

These operate on **user complaints**, not on products/orders. Used for the lab NoSQL demonstration.

- Demo script: `nosql/demo_queries.py`  
- Collection: `qop_feedback.complaints`

The main ranking pipeline reads complaints from CSV for reproducibility; MongoDB is the document-store demonstration side.

---

## Quick start

### Prerequisites

- Docker Desktop  
- Python 3.10+  
- 8 GB+ RAM recommended (use scale factor for smaller machines)

### 1. Install dependencies

bash
pip install -r requirements.txt
2. Start databases
Bash
docker compose up -d
PostgreSQL → localhost:5432
MongoDB → localhost:27017
3. Seed the e-commerce database
Bash
# Full scale (~3M rows)
python -m db.seed

# Smaller for testing (PowerShell):
# $env:QOP_SEED_SCALE="0.2"
# python -m db.seed
4. Run the pipeline
Bash
python -m nlp.complaints_data
python -m diagnostics.run_diagnostics
python -m diagnostics.measure_fixes
python -m nlp.run_nlp
python -m fusion.run_fusion
python -m fusion.prioritize
python -m eval.run_evaluation
5. Seed MongoDB (NoSQL demo)
Bash
python -m nosql.seed_mongo
python -m nosql.demo_queries
6. Start the web app
Bash
python -m app
Open [localhost](http://localhost:8000/)

Web app pages
Page	Purpose
Priorities	Ranked index fixes, α slider, summary metrics
Fix panel	Evidence, Apply / Verify / Roll back
Queries	All 25 workload queries + rank movement vs cost-only
Complaints	Browse / search / add complaints (live linking)
Evaluation	Method comparison, α-sweep, ablation
Activity	Audit log of actions
Configuration
Edit config.yaml for database connection, fusion weights (alpha), paths, and seed sizes.

Evaluation metrics
NDCG@10 — ranking quality against ideal (complaint-derived) order
Budget pain — user pain removed when fixes are applied in rank order under an effort budget
Bootstrap 95% confidence intervals
NLP link accuracy and clustering quality against held-out labels
Lab / course mapping
Requirement	How this project satisfies it
SQL	PostgreSQL 16, 8-table schema, EXPLAIN, indexes
NoSQL	MongoDB for complaints + demo queries
≥ 5–6 entities	8 entities (categories … reviews)
Innovative component	NLP (embeddings, clustering, linking)
Normalization	Schema in 3NF / BCNF
Working demo	Full web app + live apply/verify
Tests
Bash
python -m pytest tests -q
Key invariant: NLP code never reads the hidden ground-truth answer key.

Limitations
Complaints are synthetic (template-based); real tickets would be stronger
Daily call counts are an assumed traffic mix
Only index fixes are measured (no query rewrites yet)
Web app has no multi-user login
Future work
Real support tickets / app-store reviews
Real traffic from pg_stat_statements
Ticket-system integration (e.g. Jira)
Query rewrite suggestions (e.g. keyset pagination instead of deep OFFSET)

License
Academic / educational use. Built as a DBMS project.

Text

---

### How to use it

1. Open your project folder in VS Code / Notepad  
2. Replace the contents of `README.md` with the text above  
3. Save  
4. Commit and push:

```powershell
git add README.md
git commit -m "Add detailed project README"
git push
