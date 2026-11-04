"""Pure normalization. Identity-bearing suffixes and units are never dropped."""
import re
import unicodedata
from decimal import Decimal


BRANDS = ('asus', 'gigabyte', 'galax', 'msi', 'zotac', 'sapphire', 'xfx', 'asrock',
          'palit', 'pny', 'gainward', 'inno3d', 'biostar', 'amd', 'nvidia', 'intel',
          'kingston', 'corsair', 'crucial', 'adata', 'western digital', 'samsung',
          'seagate', 'lexar', 'superframe', 'redragon', 'cooler master', 'deepcool')


def normalize_text(value):
    value = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().lower()
    value = re.sub(r'https?://\S+', ' ', value)
    value = re.sub(r'[^a-z0-9.,]+', ' ', value)
    value = re.sub(r'(\d)\s+(gb|tb|mhz|w)\b', r'\1\2', value)
    value = re.sub(r'\bddr\s+(\d)', r'ddr\1', value)
    value = re.sub(r'\b(\d{4,5})\s+(x3d|kf|ks|x|g|f|k)\b', r'\1\2', value)
    value = re.sub(r'\b(?:micro\s*atx|m\s*atx)\b', 'matx', value)
    value = re.sub(r'\bmini\s*itx\b', 'itx', value)
    return re.sub(r'\s+', ' ', value).strip()


def normalize_brand(value):
    text = normalize_text(value)
    return {'wd': 'western digital', 'galaxy': 'galax', 'asustek': 'asus',
            'micro star': 'msi', 'microstar': 'msi'}.get(text, text)


def named_brands(text):
    text = normalize_text(text)
    return {b for b in BRANDS if re.search(r'\b' + re.escape(b) + r'\b', text)} | (
        {'western digital'} if re.search(r'\bwd\b', text) else set())


def normalize_store(value):
    text = normalize_text(value).replace('!', '')
    aliases = {'ka bum': 'kabum', 'kabum': 'kabum', 'terabyte shop': 'terabyte',
               'terabyteshop': 'terabyte', 'terabyte': 'terabyte', 'mercado livre': 'mercado_livre',
               'mercadolivre': 'mercado_livre', 'mercadolibre': 'mercado_livre', 'amazon brasil': 'amazon', 'amazon com br': 'amazon'}
    return aliases.get(text, text.replace(' ', '_')) or None


def capacity_values(text):
    # Binary 1024GB is equivalent to 1TB; 1000GB remains distinct.
    return {Decimal(n.replace(',', '.')) * (1024 if unit == 'tb' else 1)
            for n, unit in re.findall(r'\b(\d+(?:[.,]\d+)?)\s*(tb|gb)\b', normalize_text(text))}


def capacity_label(value):
    value = Decimal(str(value))
    return f'{value / 1024:g}TB' if value >= 1024 and value % 1024 == 0 else f'{value:g}GB'
