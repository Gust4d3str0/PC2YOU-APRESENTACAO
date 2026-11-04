from pathlib import Path
import json
root = Path(__file__).resolve().parents[1]
rows = json.loads((root/'frontend/src/presentation/snippets.json').read_text(encoding='utf-8'))
for row in rows:
    lines=(root/row['file']).read_text(encoding='utf-8-sig').splitlines()
    assert row['code'].strip() == '\n'.join(lines[row['start']-1:row['end']]).strip(), row['id']
print(f'{len(rows)} source snippets match actual files and line numbers.')
