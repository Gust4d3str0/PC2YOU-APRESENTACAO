from datetime import datetime, timezone

from scripts.preview_catalog_matches import compare_snapshots, ReadOnlyRows


def test_preview_corrects_false_high_in_memory_without_exposing_write_methods():
    old = {'id': 'ryzen-7-7800x3d', 'name': 'AMD Ryzen 7 7700', 'brand': 'AMD', 'category': 'cpu',
           'technical_specs': {}, 'compatibility': {}}
    new = {**old, 'name': 'AMD Ryzen 7 7800X3D'}
    now = datetime.now(timezone.utc)
    rows = [{'raw_text': title, 'product': {'name': title, 'component_type': 'cpu'}, 'offer': {'price': 1000},
             'telegram': {'sent_at': now}, 'created_at': now, 'status': 'parsed'}
            for title in ('AMD Ryzen 7 7700', 'AMD Ryzen 7 7800X3D')]
    report = compare_snapshots(rows, [old], [new], now)
    assert len(report['changed_decisions']) == 2
    assert report['changed_decisions'][0]['before']['match_level'] == 'high'
    assert report['changed_decisions'][0]['after']['match_level'] == 'low'
    assert report['changed_decisions'][1]['after']['match_level'] == 'high'
    assert report['mongo_written'] is False
    assert not hasattr(ReadOnlyRows(rows), 'update_one')
    assert rows[0]['product'].get('component_id') is None
