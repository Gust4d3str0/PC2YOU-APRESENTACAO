"""Export a SANITIZED snapshot of a running MongoDB into demo-data/*.jsonl (read-only on the source).

    python scripts/export_demo_data.py --mongo-uri mongodb://localhost:27017 --db orcapc_catalog --promotions 400

Telegram identifiers (chat id/name/username, message links) are replaced by a fixed pseudonym; e-mails, phones,
@handles, IPs and token-like strings are scrubbed. Only collections of the demo whitelist are read.
"""
import argparse
import re
import sys
from pathlib import Path

from bson import json_util
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api-catalogo"))
from demo.sanitize import clean_text  # noqa: E402

PSEUDO_CHAT = -1000000000001
URL_RE = re.compile(r"https?://\S+")


def scrub(value):
    """Recursive scrub that keeps BSON types (dates, Decimal128) and URLs intact."""
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, str):
        urls = URL_RE.findall(value)
        placeholders = {u: f"\u0000{i}\u0000" for i, u in enumerate(urls)}
        for url, token in placeholders.items():
            value = value.replace(url, token)
        value = clean_text(value) if len(value) < 5000 else value[:700]
        for url, token in placeholders.items():
            value = value.replace(token, url)
        return value
    return value


def pseudonymize(document):
    telegram = document.get("telegram")
    if isinstance(telegram, dict):
        telegram["chat_id"] = PSEUDO_CHAT
        telegram["chat_name"] = "Canal de ofertas (anonimizado)"
        telegram.pop("chat_username", None)
        telegram.pop("message_url", None)
    offer = document.get("offer")
    if isinstance(offer, dict):
        offer.pop("manual_validated_by", None)
    for key in ("notifications_processed_at", "notification_retry_at"):
        document.pop(key, None)
    return document


PLAN = [("components", {}, None), ("telegram_promotions", {"is_demo": {"$ne": True}}, [("created_at", -1)]),
        ("product_price_history", {}, [("date", -1)]), ("external_product_enrichment", {}, None),
        ("ml_integration_state", {}, None), ("telegram_service_status", {}, None)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mongo-uri", default="mongodb://localhost:27017")
    parser.add_argument("--db", default="orcapc_catalog")
    parser.add_argument("--promotions", type=int, default=250)
    parser.add_argument("--high", type=int, default=250)
    parser.add_argument("--history", type=int, default=300)
    parser.add_argument("--out", type=Path, default=ROOT / "demo-data")
    args = parser.parse_args()
    client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=3000)
    database = client[args.db]
    args.out.mkdir(parents=True, exist_ok=True)
    for name, selector, sort in PLAN:
        cursor = database[name].find(selector)
        if sort:
            cursor = cursor.sort(sort)
        if name == "telegram_promotions":
            cursor = cursor.limit(args.promotions)
        if name == "product_price_history":
            cursor = cursor.limit(args.history)
        found = list(cursor)
        if name == "telegram_promotions":  # recent ones plus the matched (High) ones, so the demo has real offers to show
            seen = {row["_id"] for row in found}
            high = database[name].find({**selector, "product.match_level": "high"}).sort(sort).limit(args.high)
            found += [row for row in high if row["_id"] not in seen]
        rows = [pseudonymize(scrub(row)) for row in found]
        if name == "ml_integration_state":
            for row in rows:
                row.pop("last_error", None)
        with (args.out / f"{name}.jsonl").open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json_util.dumps(row, ensure_ascii=False) + "\n")
        print(f"{name}: {len(rows)}")


if __name__ == "__main__":
    main()
