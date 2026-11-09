"""Coverage uses the same canonical field names as the deterministic rules."""
from collections import defaultdict

from .mapper import get_path
from .normalization import normalize_spec

REQUIRED = {
    'cpu': ['compatibility.socket', 'technical_specs.cores', 'technical_specs.threads', 'technical_specs.tdp_watts'],
    'motherboard': ['compatibility.socket', 'compatibility.memory_type', 'technical_specs.memory_slots',
                    'technical_specs.max_memory_gb', 'compatibility.form_factor'],
    'ram': ['technical_specs.capacity', 'compatibility.memory_type', 'technical_specs.speed'],
    'gpu': ['technical_specs.memory', 'technical_specs.length_mm', 'compatibility.min_psu_watts'],
    'psu': ['technical_specs.wattage'],
    'case': ['compatibility.supported_form_factors', 'compatibility.max_gpu_length_mm'],
    'storage': ['technical_specs.capacity', 'technical_specs.interface'],
}
RULES = [
    ('cpu_socket', [('cpu', 'compatibility', 'socket'), ('motherboard', 'compatibility', 'socket')]),
    ('ram_type', [('motherboard', 'compatibility', 'memory_type'), ('ram', 'compatibility', 'memory_type')]),
    ('ram_slots', [('motherboard', 'technical_specs', 'memory_slots'), ('ram', 'technical_specs', 'modules')]),
    ('ram_capacity', [('motherboard', 'technical_specs', 'max_memory_gb'), ('ram', 'technical_specs', 'capacity')]),
    ('gpu_power', [('gpu', 'compatibility', 'min_psu_watts'), ('psu', 'technical_specs', 'wattage')]),
    ('board_case', [('motherboard', 'compatibility', 'form_factor'), ('case', 'compatibility', 'supported_form_factors')]),
    ('gpu_case', [('gpu', 'technical_specs', 'length_mm'), ('case', 'compatibility', 'max_gpu_length_mm')]),
]


def valid_field(row, path):
    return normalize_spec(path, get_path(row, path)) is not None


def audit(rows):
    groups = defaultdict(list)
    for row in rows:
        cat = 'ram' if row.get('category') == 'kit-ram' else row.get('category')
        groups[cat].append(row)
    details, summary = [], {}
    for cat, requirements in REQUIRED.items():
        components = groups[cat]
        counts = {path: sum(valid_field(r, path) for r in components) for path in requirements}
        complete = sum(all(valid_field(r, path) for path in requirements) for r in components)
        summary[cat] = {'total': len(components), 'complete': complete, 'fields': counts}
        if cat == 'ram':
            summary[cat]['modules_known'] = sum(valid_field(r, 'technical_specs.modules') for r in components)
        for row in components:
            missing = [path for path in requirements if not valid_field(row, path)]
            details.append({'id': row['id'], 'name': row['name'], 'category': cat, 'missing': missing,
                            'modules_known': valid_field(row, 'technical_specs.modules') if cat == 'ram' else None})
    rules = {}
    for name, fields in RULES:
        required_by_category = defaultdict(list)
        for cat, section, key in fields:
            required_by_category[cat].append(f'{section}.{key}')
        rules[name] = {cat: {'eligible': sum(all(valid_field(r, p) for p in paths) for r in groups[cat]),
                             'total': len(groups[cat])} for cat, paths in required_by_category.items()}
    return {'total': len(rows), 'categories': summary, 'rules': rules, 'components': details}
