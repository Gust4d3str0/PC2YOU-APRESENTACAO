"""Benchmark exact lookup independently of Gemini or the analysis endpoint."""
import argparse
import os
from pathlib import Path

from validate_external_catalog import benchmark, read_jsonl, write_json, ROOT


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jsonl', type=Path, default=ROOT / 'reports/external-catalog-local.jsonl')
    parser.add_argument('--mongo', action='store_true')
    parser.add_argument('--db', default='pc2you_external_catalog_validation_release')
    parser.add_argument('--iterations', type=int, default=1000)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/external-lookup-benchmark.json')
    args = parser.parse_args()
    if not 1 <= args.iterations <= 100000:
        parser.error('--iterations must be 1..100000')
    if args.mongo:
        from pymongo import MongoClient
        if not os.getenv('MONGO_URI'):
            parser.error('--mongo requires explicitly exported MONGO_URI')
        with MongoClient(os.environ['MONGO_URI'], serverSelectionTimeoutMS=5000) as client:
            collection = client[args.db].components
            # Only the count is used by the benchmark, never a full-document catalog read.
            result = benchmark([None] * collection.count_documents({}), collection, args.iterations)
    else:
        result = benchmark(read_jsonl(args.jsonl), iterations=args.iterations)
    write_json(args.output, result)
    print({k: v for k, v in result.items() if k != 'explain'})
