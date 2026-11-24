.PHONY: help up down seed reset diagnose cluster rank eval demo test clean install pipeline

PYTHON := python3
COMPOSE := docker compose

help:
	@echo "Impact-Aware QOP targets:"
	@echo "  make up / down / seed / reset"
	@echo "  make diagnose / cluster / rank / eval / demo / test / pipeline"

install:
	pip install -r requirements.txt

up:
	$(COMPOSE) up -d
	@sleep 5
	@$(COMPOSE) exec -T postgres pg_isready -U qop_user -d ecommerce || true

down:
	$(COMPOSE) down

seed:
	$(PYTHON) -m db.seed

reset: down
	$(COMPOSE) down -v
	$(COMPOSE) up -d
	@sleep 8
	$(PYTHON) -m db.seed

diagnose:
	$(PYTHON) -m diagnostics.run_diagnostics

complaints:
	$(PYTHON) -m nlp.complaints_data

fixes:
	$(PYTHON) -m diagnostics.measure_fixes

cluster:
	$(PYTHON) -m nlp.run_nlp
	$(PYTHON) -m eval.nlp_eval
	$(PYTHON) -m eval.ground_truth

rank:
	$(PYTHON) -m fusion.run_fusion
	$(PYTHON) -m fusion.prioritize

eval:
	$(PYTHON) -m eval.run_evaluation

experiments:
	$(PYTHON) -m eval.experiments

demo:
	streamlit run dashboard/app.py --server.port 8501 --server.headless true

test:
	pytest tests/ -v --tb=short

clean:
	rm -f data/*.csv
	rm -rf eval/results/*
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# `fixes` needs a live Postgres (make up && make seed). Without it, fix_results.csv from the last run is reused.
pipeline: complaints diagnose cluster rank eval experiments
	@echo "Full offline pipeline complete."
mongo-seed:
	$(PYTHON) -m nosql.seed_mongo

mongo-demo:
	$(PYTHON) -m nosql.demo_queries

# optional: extend up target
up:
	$(COMPOSE) up -d
	@sleep 5
	@$(COMPOSE) exec -T postgres pg_isready -U qop_user -d ecommerce || true
	@echo "MongoDB available on localhost:27017"