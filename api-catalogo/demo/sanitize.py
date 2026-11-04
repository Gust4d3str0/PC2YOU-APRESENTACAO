"""Everything sent to /apresentacao passes through here: no personal data, tokens, contacts or private identifiers."""

import re
from datetime import date, datetime
from decimal import Decimal
from urllib.parse import urlsplit, urlunsplit

SENSITIVE_KEY = re.compile(
    r"(token|secret|password|passwd|senha|api[_-]?key|authorization|credential|session|cookie|hash|phone|telefone|"
    r"e[-_]?mail|\bip\b|ip_address|chat_id|chat_name|chat_username|message_url|validated_by|telegram_user_id|user_id|"
    r"access|refresh)", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?<![\dA-Za-z])\+?\d[\d ()-]{9,}\d(?![\dA-Za-z])")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_JWT = re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+")
_KEYS = re.compile(r"\b(?:AIza[\w-]{10,}|(?:sk|ghp|APP_USR|TG)[_-][\w-]{10,}|\d{6,}:[\w-]{20,})")
_HANDLE = re.compile(r"(?<![\w/])@[A-Za-z][\w]{3,}")
_LONG_HEX = re.compile(r"\b[0-9a-fA-F]{32,}\b")
MAX_STRING = 700
MAX_LIST = 8
MAX_KEYS = 40


def clean_text(value: str) -> str:
    def public_url(match):
        try:
            parts = urlsplit(match.group(0))
            host = parts.hostname or ''
            if host in {'localhost', '127.0.0.1'} or re.fullmatch(r'[0-9.:]+', host):
                return '[endereço privado]'
            return urlunsplit((parts.scheme, host, parts.path, '', ''))
        except ValueError:
            return '[url removida]'
    value = re.sub(r'https?://[^\s<>]+', public_url, value)
    for pattern, replacement in ((_JWT, "[token]"), (_KEYS, "[token]"), (_EMAIL, "[email]"), (_HANDLE, "[usuário]"),
                                 (_IPV4, "[ip]"), (_LONG_HEX, "[hash]"), (_PHONE, "[telefone]")):
        value = pattern.sub(replacement, value)
    return value if len(value) <= MAX_STRING else value[:MAX_STRING] + "…"


def sanitize(value, depth=0):
    """JSON-safe copy of a Mongo value with sensitive keys dropped and strings scrubbed."""
    if depth > 8:
        return None
    if isinstance(value, dict):
        items = [(k, v) for k, v in value.items() if not SENSITIVE_KEY.search(str(k))]
        return {str(k): sanitize(v, depth + 1) for k, v in items[:MAX_KEYS]}
    if isinstance(value, (list, tuple)):
        items = [sanitize(v, depth + 1) for v in value[:MAX_LIST]]
        return items + [f"… +{len(value) - MAX_LIST}"] if len(value) > MAX_LIST else items
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal) or hasattr(value, "to_decimal"):
        return float(value.to_decimal() if hasattr(value, "to_decimal") else value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)  # ObjectId and other BSON types


def sanitize_document(document: dict) -> dict:
    result = sanitize(document)
    return result if isinstance(result, dict) else {}
