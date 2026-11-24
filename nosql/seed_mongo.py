"""Seed MongoDB with complaints + optional query logs (NoSQL side of Impact-Aware QOP)."""
from __future__ import annotations
import csv
import sys
from datetime import datetime
from pathlib import Path

from pymongo import MongoClient, ASCENDING, TEXT

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "qop_feedback"

def get_db():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
    return client[DB_NAME]

def seed_complaints():
    path = ROOT / "data" / "complaints.csv"
    if not path.exists():
        print("complaints.csv not found – run nlp.complaints_data first")
        return 0

    db = get_db()
    coll = db["complaints"]
    coll.drop()

    docs = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            docs.append({
                "complaint_id": row["complaint_id"],
                "text": row["text"],
                "timestamp": row["timestamp"],
                "severity_label": int(row["severity_label"]) if row["severity_label"].isdigit() else row["severity_label"],
                "linked_query_id": row["true_query_id"],
                "source": row["source"],
            })

    if docs:
        coll.insert_many(docs)
        coll.create_index([("text", TEXT)])
        coll.create_index([("linked_query_id", ASCENDING)])
        coll.create_index([("severity_label", ASCENDING)])
        coll.create_index([("timestamp", ASCENDING)])

    print(f"Inserted {len(docs)} complaints into MongoDB → qop_feedback.complaints")
    return len(docs)

def seed_query_logs():
    """Optional: store synthetic query execution logs as documents."""
    path = ROOT / "data" / "diagnostics.csv"
    if not path.exists():
        return 0

    db = get_db()
    coll = db["query_logs"]
    coll.drop()

    docs = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            docs.append({
                "query_id": row["query_id"],
                "mean_ms": float(row.get("mean_ms") or 0),
                "calls": int(row.get("calls") or 0),
                "flags": row.get("flags", ""),
                "tech_score": float(row.get("tech_score") or 0),
                "recorded_at": datetime.utcnow().isoformat() + "Z",
            })

    if docs:
        coll.insert_many(docs)
        coll.create_index([("query_id", ASCENDING)])
        coll.create_index([("tech_score", ASCENDING)])

    print(f"Inserted {len(docs)} query logs into MongoDB → qop_feedback.query_logs")
    return len(docs)

def main():
    print("=" * 60)
    print("Impact-Aware QOP – MongoDB Seed (NoSQL)")
    print("=" * 60)
    try:
        get_db().client.admin.command("ping")
        print("MongoDB is reachable")
    except Exception as e:
        print(f"MongoDB not reachable: {e}")
        print("Start it with: docker compose up -d mongo")
        return

    seed_complaints()
    seed_query_logs()
    print("Done.")

if __name__ == "__main__":
    main()