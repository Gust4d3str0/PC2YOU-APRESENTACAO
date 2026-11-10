from pymongo import MongoClient

from config import get_settings


settings = get_settings()
client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=3000)
db = client[settings.mongo_db]
components_collection = db["components"]


def get_components_collection():
    return components_collection


def ensure_indexes(collection=None):
    target = collection if collection is not None else components_collection
    existing = target.index_information()

    def matching_indexes(field: str):
        return [
            (index_name, details)
            for index_name, details in existing.items()
            if details.get("key") == [(field, 1)]
        ]

    id_indexes = matching_indexes("id")
    if not any(details.get("unique") is True for _, details in id_indexes):
        duplicate = next(target.aggregate([
            {"$group": {"_id": "$id", "count": {"$sum": 1}}},
            {"$match": {"_id": {"$ne": None}, "count": {"$gt": 1}}},
            {"$limit": 1},
        ]), None)
        if duplicate:
            raise RuntimeError("Existem IDs duplicados; corrija os dados antes de criar o índice único")
        for index_name, _ in id_indexes:
            target.drop_index(index_name)
        target.create_index("id", unique=True, name="uq_components_id")

    for field, name in (
        ("category", "ix_components_category"),
        ("brand", "ix_components_brand"),
        ("name", "ix_components_name"),
    ):
        if not matching_indexes(field):
            target.create_index(field, name=name)

    # Additive indexes only. Populating keys is an explicit offline migration.
    for key in ('lookup_keys', 'human_lookup_keys', 'normalized_name', 'brand', 'model', 'mpn'):
        target.create_index([('category', 1), (key, 1)], name=f'ix_catalog_{key}')
    for source in ('buildcores_opendb', 'pc_part_dataset'):
        target.create_index(f'external_ids.{source}', sparse=True, name=f'ix_external_{source}')
