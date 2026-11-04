import re
import unicodedata


KEYWORDS = (
    "promoção", "oferta", "cupom", "desconto", "pix", "kabum", "pichau",
    "terabyte", "amazon", "mercado livre", "placa de vídeo", "gpu",
    "processador", "cpu", "ssd", "memória", "ram", "fonte", "placa mãe",
    "motherboard",
)


def normalize_text(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(char)
    )


_KEYWORD_RE = re.compile(
    r"(?<!\w)(?:" + "|".join(re.escape(normalize_text(word)) for word in KEYWORDS) + r")(?!\w)"
)


def is_possible_promotion(text: object) -> bool:
    if not isinstance(text, str) or not text.strip():
        return False
    normalized = normalize_text(text)
    return "r$" in normalized or bool(_KEYWORD_RE.search(normalized))
