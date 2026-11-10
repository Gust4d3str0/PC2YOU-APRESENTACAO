"""Offline published PC Part Dataset ingestion; never executes the scraper."""
from import_external_catalog import main

if __name__ == '__main__':
    raise SystemExit(main('pc_part_dataset'))
