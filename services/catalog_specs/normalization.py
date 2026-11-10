"""One parser for catalog specs. Unknown units, ranges and alternatives fail closed."""
import re
import unicodedata
from decimal import Decimal, InvalidOperation


def text(value):
    return unicodedata.normalize('NFKC', str(value)).strip()


def number(value, units=('',), *, integer=True):
    if isinstance(value, bool) or value is None:
        return None
    match = re.fullmatch(r'\s*(\d+(?:[.,]\d+)?)\s*(' + '|'.join(re.escape(u) for u in units) + r')\s*', text(value), re.I)
    if not match:
        return None
    try:
        result = Decimal(match[1].replace(',', '.'))
    except InvalidOperation:
        return None
    if result <= 0 or (integer and result != int(result)):
        return None
    return int(result) if result == int(result) else float(result)


def capacity(value, *, gb=False):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        amount, unit = number(value, integer=False), 'GB'
    else:
        match = re.fullmatch(r'(\d+(?:[.,]\d+)?)\s*(GB|TB)', text(value), re.I)
        if not match:
            return None
        amount, unit = number(match[1], integer=False), match[2].upper()
    if amount is None:
        return None
    if gb:
        result = amount * (1024 if unit == 'TB' else 1)
        return int(result) if result == int(result) else None
    return f'{amount:g}{unit}'


def normalize_spec(key, value):
    """Normalize a value according to its destination, never infer missing facts."""
    key = key.rsplit('.', 1)[-1]
    if value is None or isinstance(value, (bool, dict)):
        return None
    if key == 'socket':
        compact = re.sub(r'[\s-]', '', text(value)).upper()
        compact = compact.removeprefix('SOCKET').removesuffix('SOCKET')
        compact = re.sub(r'^FCLGA', 'LGA', compact)
        return compact if re.fullmatch(r'(?:AM[2345]|FM[12]\+?|LGA\d{3,4}|TR[45]|STRX4|STR5)', compact) else None
    if key == 'memory_type':
        compact = re.sub(r'\s', '', text(value)).upper().removesuffix('SDRAM')
        return compact if re.fullmatch(r'DDR[2345]', compact) else None
    if key == 'form_factor':
        compact = re.sub(r'[\s_-]', '', text(value)).upper()
        return {'ATX': 'ATX', 'MICROATX': 'Micro-ATX', 'MATX': 'Micro-ATX', 'MINIITX': 'Mini-ITX',
                'ITX': 'Mini-ITX', 'EATX': 'E-ATX', 'EXTENDEDATX': 'E-ATX'}.get(compact)
    if key == 'supported_form_factors':
        parts = value if isinstance(value, list) else re.split(r'[,;/]', text(value))
        normalized = [normalize_spec('form_factor', part) for part in parts]
        return list(dict.fromkeys(normalized)) if normalized and all(normalized) else None
    if key in {'wattage', 'tdp_watts', 'min_psu_watts', 'power_consumption_watts'}:
        return number(value, ('', 'W', 'watts'))
    if key in {'length_mm', 'max_gpu_length_mm'}:
        result = number(value, ('', 'mm'), integer=False)
        if result is None:
            cm = number(value, ('cm',), integer=False)
            result = round(cm * 10, 3) if cm else None
        return result
    if key in {'capacity', 'vram'}:
        return capacity(value)
    if key == 'memory':
        match = re.fullmatch(r'(\d+(?:[.,]\d+)?\s*(?:GB|TB))(?:\s+(GDDR[34567]X?))?', text(value), re.I)
        if not match:
            return None
        return capacity(match[1]) + (' ' + match[2].upper() if match[2] else '')
    if key == 'max_memory_gb':
        return capacity(value, gb=True)
    if key == 'memory_slots':
        result = number(value)
        if result is not None:
            return result
        match = re.fullmatch(r'(\d+)\s*(?:x\s*(?:DIMM|slots)|slots(?:\s+DDR[345])?)', text(value), re.I)
        return int(match[1]) if match and int(match[1]) > 0 else None
    if key in {'cores', 'threads'}:
        return number(value)
    if key == 'modules':
        count = number(value)
        if count:
            return count
        match = re.fullmatch(r'(\d+)\s*[xX×]\s*(\d+)\s*GB', text(value))
        return f'{int(match[1])}x{int(match[2])}GB' if match and int(match[1]) > 0 and int(match[2]) > 0 else None
    if key in {'speed', 'max_memory_speed'}:
        speed = number(value, ('', 'MHz', 'MT/s'))
        if speed is None:
            ghz = number(value, ('GHz',), integer=False)
            speed = round(ghz * 1000) if ghz and ghz * 1000 == round(ghz * 1000) else None
        return f'{speed}MHz' if speed else None
    if key in {'interface', 'pcie_version'}:
        compact = re.sub(r'\s+', ' ', text(value)).upper()
        compact = re.sub(r'PCI[- ]?(?:EXPRESS|E)', 'PCIE', compact)
        match = re.fullmatch(r'(?:NVME\s*\(PCIE GEN ([345]) X4\)|PCIE ([345])\.0, NVME 1\.[34])', compact)
        if match:
            return f'NVMe PCIe {match[1] or match[2]}.0'
        if re.fullmatch(r'(?:NVME )?PCIE [345]\.0(?: X(?:4|8|16))?', compact):
            return compact.replace('PCIE', 'PCIe').replace('NVME', 'NVMe').replace(' X', ' x')
        return {'SATA': 'SATA', 'SATA III': 'SATA III', 'SATA 3': 'SATA III', 'SATA3': 'SATA III',
                'NVME': 'NVMe', 'M.2': 'M.2'}.get(compact)
    return None
