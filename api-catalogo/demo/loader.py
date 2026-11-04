"""Loads the sanitized snapshot (demo-data/*.jsonl) into an EMPTY database. Never overwrites existing promotions."""

from pathlib import Path

from bson import json_util

from database import db

DATA_DIR = Path(__file__).resolve().parents[1] / "demo-data"
if not DATA_DIR.is_dir():
    DATA_DIR = Path(__file__).resolve().parents[2] / "demo-data"
COLLECTIONS = ("telegram_promotions", "product_price_history", "external_product_enrichment",
               "ml_integration_state", "telegram_service_status")


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as handle:
        return [json_util.loads(line) for line in handle if line.strip()]


def load_demo_data(database=None, data_dir: Path | None = None) -> dict:
    database = database if database is not None else db
    data_dir = data_dir or DATA_DIR
    if not data_dir.is_dir():
        return {"loaded": False, "reason": "no_demo_data"}
    if database["telegram_promotions"].estimated_document_count() > 0:
        return {"loaded": False, "reason": "database_not_empty"}
    summary = {}
    for name in COLLECTIONS:
        file = data_dir / f"{name}.jsonl"
        rows = read_jsonl(file) if file.is_file() else []
        if rows:
            database[name].insert_many(rows, ordered=False)
        summary[name] = len(rows)
    components_file = data_dir / "components.jsonl"
    if components_file.is_file():
        for row in read_jsonl(components_file):
            row.pop("_id", None)
            database["components"].replace_one({"id": row["id"]}, row, upsert=True)
            summary["components"] = summary.get("components", 0) + 1
    return {"loaded": True, **summary}
