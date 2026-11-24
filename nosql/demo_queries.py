"""Demonstration MongoDB queries for Component 4 (NoSQL Test) – Impact-Aware QOP."""
from __future__ import annotations
from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017")
db = client["qop_feedback"]

print("=" * 60)
print("Impact-Aware QOP – MongoDB Demo Queries (NoSQL)")
print("=" * 60)

# 1. High severity complaints
print("\n=== 1. High severity complaints ===")
cursor = db.complaints.find({"severity_label": 2}).limit(5)
for doc in cursor:
    print(f"  {doc['complaint_id']}: {doc['text'][:70]}...")

# 2. Complaints linked to a specific slow query (Q06 – search)
print("\n=== 2. Complaints linked to Q06 (product search) ===")
cursor = db.complaints.find({"linked_query_id": "Q06"})
for doc in cursor:
    print(f"  {doc['complaint_id']}: {doc['text'][:70]}...")

# 3. Aggregation – complaint count per query
print("\n=== 3. Complaint count per query (Aggregation) ===")
pipeline = [
    {"$group": {"_id": "$linked_query_id", "count": {"$sum": 1}}},
    {"$sort": {"count": -1}},
    {"$limit": 8},
]
for row in db.complaints.aggregate(pipeline):
    print(f"  {row['_id']}: {row['count']} complaints")

# 4. Text search
print("\n=== 4. Text search for 'slow' or 'checkout' ===")
try:
    cursor = db.complaints.find({"$text": {"$search": "slow checkout"}}).limit(5)
    for doc in cursor:
        print(f"  {doc['complaint_id']}: {doc['text'][:70]}...")
except Exception as e:
    print(f"  Text index may be missing: {e}")
    print("  Falling back to regex search...")
    cursor = db.complaints.find({"text": {"$regex": "slow|checkout", "$options": "i"}}).limit(5)
    for doc in cursor:
        print(f"  {doc['complaint_id']}: {doc['text'][:70]}...")

# 5. Top technical scores from query_logs
print("\n=== 5. Top technical severity scores (from query_logs) ===")
cursor = db.query_logs.find().sort("tech_score", -1).limit(5)
for doc in cursor:
    print(f"  {doc['query_id']}: tech_score={doc['tech_score']:.3f} | flags={doc.get('flags', '')}")

# 6. Recent complaints
print("\n=== 6. Most recent complaints ===")
cursor = db.complaints.find().sort("timestamp", -1).limit(3)
for doc in cursor:
    print(f"  {doc.get('timestamp', '')[:10]} | {doc['complaint_id']}: {doc['text'][:55]}...")

# 7. Count summary
print("\n=== 7. Collection summary ===")
print(f"  Total complaints : {db.complaints.count_documents({})}")
print(f"  Total query logs : {db.query_logs.count_documents({})}")

print("\n" + "=" * 60)
print("NoSQL demo completed successfully.")
print("=" * 60)