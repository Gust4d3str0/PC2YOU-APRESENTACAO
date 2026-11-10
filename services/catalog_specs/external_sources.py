"""Bounded, checksum-verified snapshot readers and source-to-canonical adapters."""
from datetime import date
import hashlib
import json
from pathlib import Path
import re

from .external_identity import cpu_model, gpu_model, internal_id, valid_mpn
from .normalization import normalize_spec, number
from product_matching.normalization import normalize_brand

POLICY = json.loads(Path(__file__).with_name('import_policy.json').read_text(encoding='utf-8'))
IMPORT_CATEGORIES = set(POLICY['categories'])
BUILD_CATEGORIES = dict(cpu='CPU', gpu='GPU', motherboard='Motherboard', ram='RAM', storage='Storage', psu='PSU', case='PCCase')
DATASET_CATEGORIES = dict(cpu='cpu', gpu='video-card', motherboard='motherboard', ram='memory', storage='internal-hard-drive', psu='power-supply', case='case')
EXTERNAL_KEYS = {'buildcores': 'buildcores_opendb', 'pc_part_dataset': 'pc_part_dataset'}
LICENSES = {'buildcores': 'CC-BY-NC-SA-4.0', 'pc_part_dataset': 'MIT'}
BRANDS = sorted(('AMD', 'Intel', 'NVIDIA', 'ASUS', 'ASRock', 'Gigabyte', 'MSI', 'Sapphire', 'XFX', 'Zotac',
    'EVGA', 'PNY', 'Palit', 'PowerColor', 'Inno3D', 'Gainward', 'Galax', 'Kingston', 'Corsair', 'G.Skill',
    'Crucial', 'ADATA', 'Western Digital', 'WD', 'Samsung', 'Seagate', 'Lexar', 'TEAMGROUP', 'Team',
    'Cooler Master', 'Deepcool', 'be quiet!', 'Fractal Design', 'Lian Li', 'NZXT', 'Montech', 'Phanteks',
    'Thermaltake', 'Antec', 'Silverstone', 'SilverStone', 'FSP Group', 'SeaSonic', 'Seasonic', 'Super Flower',
    'KIOXIA', 'Inland', 'Patriot', 'Silicon Power', 'Apacer', 'Biostar', 'HYTE', 'Aerocool'), key=len, reverse=True)


def bounded_json(path, limit):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > limit:
        raise ValueError('file_size_or_symlink')
    data = path.read_bytes()
    if len(data) > limit:
        raise ValueError('file_size')
    return json.loads(data, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('non_finite_json'))), hashlib.sha256(data).hexdigest()


class Snapshot:
    def __init__(self, path, source):
        self.path, self.source = Path(path).resolve(), source
        self.metadata, _ = bounded_json(self.path / 'snapshot.json', 16 * 1024 * 1024)
        if self.metadata.get('source') != source or self.metadata.get('license') != LICENSES[source]:
            raise ValueError('source_or_license_mismatch')
        if not re.fullmatch(r'[a-f0-9]{40}', self.metadata.get('commit', '')):
            raise ValueError('immutable_commit_required')
        self.bytes_read = 0

    def read(self, relative):
        path = (self.path / relative).resolve()
        if not path.is_relative_to(self.path):
            raise ValueError('unsafe_path')
        self.bytes_read += path.stat().st_size
        if self.bytes_read > POLICY['max_snapshot_bytes']:
            raise ValueError('snapshot_byte_limit')
        data, checksum = bounded_json(path, POLICY['max_file_bytes'])
        if self.metadata['files'].get(Path(relative).as_posix()) != checksum:
            raise ValueError('checksum_mismatch')
        return data

    def records(self, categories, limit=None):
        count = 0
        for category in sorted(categories):
            if self.source == 'buildcores':
                from jsonschema import Draft7Validator, FormatChecker
                folder = BUILD_CATEGORIES[category]
                schema = self.read(f'schemas/{folder}.schema.json')
                if '"$ref"' in json.dumps(schema):
                    raise ValueError('schema_references_disabled')
                Draft7Validator.check_schema(schema)
                validator = Draft7Validator(schema, format_checker=FormatChecker())
                records = ((str(p.relative_to(self.path)), p.stem) for p in sorted((self.path / 'open-db' / folder).glob('*.json')))
            else:
                filename = f'data/json/{DATASET_CATEGORIES[category]}.json'
                data = self.read(filename)
                if not isinstance(data, list) or len(data) > POLICY['max_records']:
                    raise ValueError('dataset_array_required_or_too_large')
                records = ((filename, (i, row)) for i, row in enumerate(data))
                validator = None
            for filename, record in records:
                if count >= min(limit or POLICY['max_records'], POLICY['max_records']):
                    return
                count += 1
                try:
                    if self.source == 'buildcores':
                        row = self.read(filename)
                        if not isinstance(row, dict) or row.get('opendb_id') != record:
                            raise ValueError('record_id_filename_mismatch')
                        error = next(validator.iter_errors(row), None)
                        if error:
                            raise ValueError(f'schema:{".".join(map(str, error.absolute_path))}:{error.validator}')
                        external_id = record
                    else:
                        index, row = record
                        validate_dataset(row, category)
                        # Dataset has no IDs. Hash the complete noncommercial record, never price or array position.
                        facts = {k: v for k, v in row.items() if k not in {'price', 'price_per_gb'}}
                        external_id = hashlib.sha256((category + json.dumps(facts, sort_keys=True)).encode()).hexdigest()
                    if len(json.dumps(row).encode()) > POLICY['max_record_bytes']:
                        raise ValueError('record_size_limit')
                    yield category, external_id, row, filename, None
                except (ValueError, TypeError, OSError, RecursionError) as exc:
                    yield category, str(record if self.source == 'buildcores' else record[0]), None, filename, str(exc)[:180]


def validate_dataset(row, category):
    """Explicit local contract for the published dataset (which ships no JSON schemas)."""
    from jsonschema import Draft7Validator
    numeric = {'type': ['number', 'null'], 'minimum': 0}
    properties = {'name': {'type': 'string', 'minLength': 3, 'maxLength': 1000}}
    for key in {'core_count', 'core_clock', 'boost_clock', 'tdp', 'memory', 'length', 'capacity', 'max_memory', 'memory_slots', 'wattage', 'cas_latency'}:
        properties[key] = numeric
    for key in {'socket', 'form_factor', 'chipset', 'type', 'interface', 'color', 'microarchitecture'}:
        properties[key] = {'type': ['string', 'null'], 'maxLength': 1000}
    for key in {'speed', 'modules'}:
        properties[key] = {'type': ['array', 'null'], 'minItems': 2, 'maxItems': 2, 'items': {'type': 'number', 'exclusiveMinimum': 0}}
    error = next(Draft7Validator({'type': 'object', 'required': ['name'], 'properties': properties}).iter_errors(row), None)
    if error:
        raise ValueError(f'schema:{".".join(map(str, error.absolute_path))}:{error.validator}')


def _path(row, path):
    for key in path.split('.'):
        if not isinstance(row, dict):
            return None
        row = row.get(key)
    return row


def _storage_capacity(value):
    # Both datasets specify decimal GB. Do not turn a marketed 1000GB SSD into 1024GB.
    amount = number(value, integer=False)
    return (f'{amount / 1000:g}TB' if amount >= 1000 and amount % 1000 == 0 else f'{amount:g}GB') if amount else None


def _storage_interface(raw):
    if not isinstance(raw, str):
        return None
    if re.fullmatch(r'M\.2 PCIe [345]\.0 [xX][1248]', raw, re.I):
        return raw[4:]
    return {'SATA 6.0 Gb/s': 'SATA III', 'SATA 6 Gb/s': 'SATA III', 'M.2 SATA': 'SATA'}.get(raw, raw)


def adapt(source, category, raw, external_id, snapshot, imported_at, newer_than=None):
    build = source == 'buildcores'
    name = _path(raw, 'metadata.name') if build else raw['name']
    if not isinstance(name, str) or not name.strip() or len(name) > 500:
        raise ValueError('missing_or_oversized_identity')
    brand = _path(raw, 'metadata.manufacturer') if build else next((b for b in BRANDS if name.casefold().startswith(b.casefold() + ' ')), None)
    if not brand:
        raise ValueError('missing_manufacturer')
    if re.search(r'\b(?:laptop|notebook|mobile|server|xeon|epyc|threadripper|opteron|tesla|quadro|firepro|sodimm|so-dimm|registered|ecc registered)\b', name, re.I):
        raise ValueError('outside_desktop_scope')
    year = _path(raw, 'metadata.releaseYear') if build else None
    if year and year < POLICY['minimum_release_year']:
        raise ValueError('obsolete_release')
    if newer_than:
        observed = _path(raw, 'metadata.last_manually_spec_verified_at') if build else raw.get('release_date')
        if observed:
            recent = date.fromisoformat(observed[:10]) >= newer_than
        elif year:
            recent = date(int(year), 1, 1) >= newer_than
        else:
            raise ValueError('date_unavailable')
        if not recent:
            raise ValueError('older_than_filter')
    row = dict(name=name.strip(), brand=normalize_brand(brand), category=category, image='/components/default-component.png',
               description='', technical_specs={}, compatibility={}, prices=[], price_history=[], benchmark={}, aliases=[name.strip()],
               external_ids={EXTERNAL_KEYS[source]: [external_id]}, spec_provenance={}, identity_scope='sku', mpn=[])
    lineage = dict(source=source, source_id=external_id, commit=snapshot['commit'], license=snapshot['license'], imported_at=imported_at)

    def put(destination, value, source_field, *, parsed=False):
        value = normalize_spec(destination, value)
        if value is None:
            return
        section, key = destination.split('.')
        bounds = {'cores': 256, 'threads': 512, 'wattage': 3000, 'tdp_watts': 1500,
                  'length_mm': 600, 'max_gpu_length_mm': 1000, 'memory_slots': 16, 'max_memory_gb': 2048}
        if key in bounds and isinstance(value, (int, float)) and value > bounds[key]:
            raise ValueError('implausible_' + key)
        row[section][key] = value
        row['spec_provenance'][destination.replace('.', '__')] = {**lineage, 'field': destination, 'source_field': source_field,
            'sources': [source], 'method': 'deterministic_name' if parsed else 'structured'}

    if build:
        identifiers = _path(raw, 'identifiers.identifiers') or []
        row['mpn'] = sorted({i['value'] for i in identifiers if i.get('type') == 'mpn'} | set(_path(raw, 'metadata.part_numbers') or []))
        # UUIDs and display names sometimes appear in upstream part_numbers; they are not MPNs.
        row['mpn'] = [v for v in row['mpn'] if valid_mpn(v, category) and v.casefold() != name.casefold()
                      and not re.fullmatch(r'[a-f0-9-]{36}', v, re.I)]
    if category == 'cpu':
        vendors = set(re.findall(r'\b(amd|intel)\b', name.casefold()))
        if vendors and vendors != {normalize_brand(brand)}:
            raise ValueError('cpu_manufacturer_conflict')
        model = cpu_model(name)
        if not model:
            raise ValueError('unsupported_desktop_cpu_identity')
        compact = re.sub(r'[^a-z0-9]', '', name.lower())
        if re.search(r'\d{3,5}(?:u|h|hs|hx|hk|mq|hq|m)(?:\b|$)', name.lower()) or 'pro' in name.lower().split():
            raise ValueError('mobile_or_workstation_cpu')
        intel = re.search(r'i[3579](\d{4,5})', compact)
        if intel and int(intel[1]) < 8000:
            raise ValueError('obsolete_cpu')
        socket = raw.get('socket')
        if socket and normalize_spec('socket', socket) not in POLICY['desktop_sockets']:
            raise ValueError('unsupported_desktop_socket')
        row['identity_scope'] = 'model'
        for dst, src in [('compatibility.socket', 'socket'), ('technical_specs.cores', 'cores.total' if build else 'core_count'),
                         ('technical_specs.threads', 'cores.threads' if build else 'thread_count'),
                         ('technical_specs.tdp_watts', 'specifications.tdp' if build else 'tdp')]:
            put(dst, _path(raw, src), src)
    elif category == 'gpu':
        chip = raw.get('chipset') or name
        if not gpu_model(chip) or (gpu_model(name) and gpu_model(name) != gpu_model(chip)):
            raise ValueError('unsupported_or_conflicting_gpu_chipset')
        if not gpu_model(name):
            row['name'] += ' ' + chip
            row['aliases'].append(row['name'])
        generic = re.sub(r'\b(?:nvidia|amd|intel|geforce|radeon)\b', '', name, flags=re.I).strip()
        if re.fullmatch(r'(?:RTX|GTX|RX|ARC)\s*[AB]?\d{3,4}(?:\s+(?:Ti|Super|XT|XTX|GRE))*(?:\s+\d+\s*GB)?', generic, re.I):
            row['identity_scope'] = 'family'
        chip_number = re.search(r'(rtx|gtx|rx)\s*(\d+)', chip, re.I)
        if chip_number and ((chip_number[1].lower() == 'gtx' and int(chip_number[2]) < 1000) or (chip_number[1].lower() == 'rx' and int(chip_number[2]) < 500)):
            raise ValueError('obsolete_gpu')
        put('technical_specs.memory', f"{raw['memory']}GB" if raw.get('memory') else None, 'memory')
        if row['identity_scope'] == 'sku':
            put('technical_specs.length_mm', raw.get('length'), 'length')
        put('technical_specs.tdp_watts', raw.get('tdp'), 'tdp')
    elif category == 'motherboard':
        socket = normalize_spec('socket', raw.get('socket'))
        if socket not in POLICY['desktop_sockets']:
            raise ValueError('unsupported_desktop_socket')
        for dst, src in [('compatibility.socket', 'socket'), ('compatibility.form_factor', 'form_factor'),
                         ('compatibility.memory_type', 'memory.ram_type' if build else 'memory_type'),
                         ('technical_specs.memory_slots', 'memory.slots' if build else 'memory_slots'),
                         ('technical_specs.max_memory_gb', 'memory.max' if build else 'max_memory')]:
            put(dst, _path(raw, src), src)
        if not row['compatibility'].get('memory_type'):
            matches = re.findall(r'\bDDR\s*([45])\b', name, re.I)
            if len(set(matches)) == 1:
                put('compatibility.memory_type', 'DDR' + matches[0], 'name', parsed=True)
            else:
                raise ValueError('board_ddr_variant_unknown')
    elif category == 'ram':
        form = raw.get('form_factor')
        if not form or 'SO' in form.upper() or not re.search(r'\b(?:U?DIMM)\b', form, re.I):
            raise ValueError('desktop_dimm_not_confirmed')
        if raw.get('registered') in {'Registered', 'Load Reduced'}:
            raise ValueError('server_memory')
        put('compatibility.memory_type', raw.get('ram_type'), 'ram_type')
        put('technical_specs.capacity', raw.get('capacity'), 'capacity')
        put('technical_specs.speed', raw.get('speed'), 'speed')
        modules = raw.get('modules') or {}
        qty, each = number(modules.get('quantity')), number(modules.get('capacity_gb'))
        if qty and each:
            if raw.get('capacity') != qty * each:
                raise ValueError('kit_capacity_conflict')
            put('technical_specs.modules', f'{qty}x{each}GB', 'modules')
        put('technical_specs.cas_latency', raw.get('cas_latency'), 'cas_latency')
        if row['compatibility'].get('memory_type') not in {'DDR4', 'DDR5'}:
            raise ValueError('obsolete_memory')
    elif category == 'storage':
        if raw.get('storage_type' if build else 'type') != 'SSD':
            raise ValueError('non_ssd_storage')
        put('technical_specs.capacity', _storage_capacity(raw.get('capacity')), 'capacity')
        put('technical_specs.interface', _storage_interface(raw.get('interface')), 'interface')
        if not row['technical_specs'].get('interface'):
            raise ValueError('unsupported_storage_interface')
    elif category == 'psu':
        if raw.get('form_factor' if build else 'type') not in {'ATX', 'ATX/EPS', 'SFX', 'SFX-L'}:
            raise ValueError('unsupported_psu_form')
        put('technical_specs.wattage', raw.get('wattage'), 'wattage')
    elif category == 'case':
        put('compatibility.supported_form_factors', raw.get('supported_motherboard_form_factors'), 'supported_motherboard_form_factors')
        put('compatibility.max_gpu_length_mm', raw.get('max_video_card_length'), 'max_video_card_length')
    if not row['technical_specs'] and not row['compatibility']:
        raise ValueError('no_useful_compatibility_fields')
    if category in {'gpu', 'ram', 'storage'} and not row['technical_specs'].get('memory' if category == 'gpu' else 'capacity'):
        raise ValueError('capacity_required_for_identity')
    # Preserve source variants without converting physical properties into identity guesses.
    if build:
        variant = _path(raw, 'metadata.manufacturer_color')
    else:
        variant = raw.get('color')
    if variant:
        row['identity_variant'] = variant.casefold().strip()
    for field in ('name', 'brand', 'category', 'identity_scope', 'mpn', 'identity_variant'):
        if row.get(field):
            row['spec_provenance'][field] = {**lineage, 'sources': [source], 'method': 'source_identity'}
    row['id'] = internal_id(row)
    return row
