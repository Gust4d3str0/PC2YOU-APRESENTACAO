"""Complete one known demo field; dry-run by default, no inserts or overwrites.

python scripts/backfill_demo_specs.py --apply
python scripts/backfill_demo_specs.py --mongo-uri mongodb://localhost:27017 --db orcapc_catalog --apply

Source: scripts/ai_upgrade_demo.py, mock_app/current, SAME b550m-am4-ddr4 ID:
technical_specs.max_memory_gb = 128. This is a repository demo reference, not
independent verification of a commercial motherboard SKU. No external lookup.
"""
import argparse
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPONENT_ID = "b550m-am4-ddr4"
FIELD = "technical_specs.max_memory_gb"
VALUE = 128


def missing_fields(row):
    if row.get("id") != COMPONENT_ID or row.get("category") != "motherboard":
        return {}
    specs = row.get("technical_specs")
    if specs is not None and not isinstance(specs, dict):
        return {}  # Malformed data needs review, not a speculative repair.
    if (specs or {}).get("max_memory_gb") in (None, ""):
        return {FIELD: VALUE}
    return {}


def backfill_jsonl(path, apply=False):
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    changes = []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        row = json.loads(line)
        fields = missing_fields(row)
        if fields:
            changes.append({"id": row["id"], "fields": fields})
            row.setdefault("technical_specs", {})
            if row["technical_specs"] is None:
                row["technical_specs"] = {}
            row["technical_specs"]["max_memory_gb"] = VALUE
            lines[index] = json.dumps(row, ensure_ascii=False) + "\n"
    if apply and changes:
        path.write_text("".join(lines), encoding="utf-8")
    return changes


def backfill_collection(collection, apply=False):
    changes = []
    for row in collection.find({"id": COMPONENT_ID, "category": "motherboard"}):
        fields = missing_fields(row)
        if fields:
            changes.append({"id": row["id"], "fields": fields})
            if apply:
                # Compare-and-set: never replace a value added since the read.
                if "technical_specs" in row and row["technical_specs"] is None:
                    collection.update_one({"_id": row["_id"], "technical_specs": None},
                                          {"$set": {"technical_specs": {"max_memory_gb": VALUE}}})
                else:
                    collection.update_one({"_id": row["_id"], FIELD: (row.get("technical_specs") or {}).get("max_memory_gb")},
                                          {"$set": fields})
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--jsonl", type=Path, default=ROOT / "demo-data/components.jsonl")
    parser.add_argument("--mongo-uri", help="Optional persisted demo database; otherwise patches the local snapshot")
    parser.add_argument("--db", default=os.getenv("MONGO_DB", "orcapc_catalog"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.mongo_uri:
        from pymongo import MongoClient
        with MongoClient(args.mongo_uri, serverSelectionTimeoutMS=3000) as client:
            changes = backfill_collection(client[args.db].components, args.apply)
    else:
        changes = backfill_jsonl(args.jsonl, args.apply)
    print(json.dumps({"mode": "apply" if args.apply else "dry-run", "changes": changes}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
