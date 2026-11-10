"""Download immutable data snapshots only; never extract or execute upstream code."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile

import requests

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    'buildcores': ('buildcores/buildcores-open-db', 'CC-BY-NC-SA-4.0'),
    'pc_part_dataset': ('docyx/pc-part-dataset', 'MIT'),
}
MAX_DOWNLOAD = 128 * 1024 * 1024
MAX_EXPANDED = 256 * 1024 * 1024
MAX_FILE = 24 * 1024 * 1024


def fetch(source, commit, destination):
    if not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise ValueError('Use an immutable full 40-character commit SHA')
    repo, license_id = SOURCES[source]
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Destination must not exist; snapshots are immutable')
    with tempfile.TemporaryFile() as archive:
        sha, size = hashlib.sha256(), 0
        with requests.get(f'https://codeload.github.com/{repo}/zip/{commit}', stream=True, timeout=(10, 90)) as response:
            response.raise_for_status()
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > MAX_DOWNLOAD:
                    raise ValueError('Snapshot download exceeds byte limit')
                sha.update(chunk)
                archive.write(chunk)
        archive.seek(0)
        with zipfile.ZipFile(archive) as bundle:
            selected, total = [], 0
            for entry in bundle.infolist():
                if entry.is_dir():
                    continue
                parts = PurePosixPath(entry.filename).parts[1:]
                if not parts or any(p in {'.', '..'} or ':' in p or '\\' in p for p in parts):
                    raise ValueError('Unsafe snapshot path')
                path = PurePosixPath(*parts)
                allowed = (path.parts[0] in {'open-db', 'schemas', 'data'} and path.suffix == '.json') or (
                    path.suffix.lower() in {'.md', '.txt', ''} and
                    (path.parts[0] in {'docs'} or path.name in {'README.md', 'LICENSE', 'LICENSE.txt', 'NOTICE.md'}))
                if not allowed:
                    continue
                total += entry.file_size
                if entry.file_size > MAX_FILE or total > MAX_EXPANDED or len(selected) >= 100000:
                    raise ValueError('Snapshot expansion exceeds resource limits')
                if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Symlinks are not allowed')
                selected.append((entry, path))
            destination.mkdir(parents=True)
            files = {}
            for entry, path in selected:
                data = bundle.read(entry)
                target = destination.joinpath(*path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                files[str(path)] = hashlib.sha256(data).hexdigest()
    metadata = {'source': source, 'repository': repo, 'commit': commit, 'license': license_id,
                'downloaded_at': datetime.now(timezone.utc).isoformat(), 'archive_sha256': sha.hexdigest(),
                'download_bytes': size, 'files': files}
    (destination / 'snapshot.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    return {k: v for k, v in metadata.items() if k != 'files'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', choices=SOURCES, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(fetch(args.source, args.commit, args.output)))
