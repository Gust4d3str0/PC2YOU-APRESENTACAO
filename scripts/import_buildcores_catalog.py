"""Offline BuildCores structured snapshot ingestion; dry-run is the default."""
from import_external_catalog import main

if __name__ == '__main__':
    raise SystemExit(main('buildcores'))
