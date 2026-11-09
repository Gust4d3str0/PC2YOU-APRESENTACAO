"""Classify existing identities; classification never creates a technical specification."""
import re
import unicodedata


def identity_scope(row):
    if row.get('identity_scope'):
        scope = row['identity_scope']
        return 'family' if scope in {'gpu-model-and-vram-class', 'chipset-memory-form-factor-class'} else scope
    category = row.get('category')
    name = unicodedata.normalize('NFKD', row.get('name', '')).encode('ascii', 'ignore').decode().lower()
    if category == 'cpu':
        return 'model'
    if category == 'gpu' and re.fullmatch(r'(?:geforce |radeon )?(?:rtx|gtx|rx)\s*\d{4}(?:\s*(?:ti|super|xt|xtx|gre))*(?:\s*\d+gb)?', name):
        return 'family'
    if category == 'motherboard' and (('(classe)' in name) or re.fullmatch(r'placa.mae [abhxz]\d{3}[a-z]* (?:am\d|lga\d+) ddr\d', name)):
        return 'family'
    if category == 'psu' and name.startswith('fonte '):
        return 'family'
    if 'modelo a definir' in name or 'compacto' in name:
        return 'family'
    return 'sku'
