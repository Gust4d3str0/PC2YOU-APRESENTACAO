import os
from dataclasses import dataclass
from functools import lru_cache


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} deve ser um número inteiro.") from exc
    if value <= 0:
        raise RuntimeError(f"{name} deve ser maior que zero.")
    return value


def _nonnegative_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} deve ser um número inteiro.") from exc
    if value < 0:
        raise RuntimeError(f"{name} não pode ser negativo.")
    return value


def _origins() -> tuple[str, ...]:
    raw = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://frontend:5173",
    )
    origins = tuple(origin.strip() for origin in raw.split(",") if origin.strip())
    if not origins or "*" in origins:
        raise RuntimeError("CORS_ORIGINS deve listar origens explícitas.")
    return origins


@dataclass(frozen=True)
class Settings:
    mongo_uri: str
    mongo_db: str
    jwt_secret: str
    jwt_algorithm: str
    admin_api_key: str
    cors_origins: tuple[str, ...]
    max_page_size: int
    max_batch_size: int
    max_search_length: int
    proxy_max_bytes: int
    proxy_connect_timeout: int
    proxy_read_timeout: int
    ml_connect_timeout: int
    ml_read_timeout: int
    refresh_cooldown_seconds: int


@lru_cache
def get_settings() -> Settings:
    algorithm = os.getenv("JWT_ALGORITHM", "HS256").strip()
    if algorithm not in {"HS256", "HS384", "HS512"}:
        raise RuntimeError("JWT_ALGORITHM deve usar um algoritmo HMAC permitido.")
    return Settings(
        mongo_uri=os.getenv("MONGO_URI", "mongodb://localhost:27017").strip(),
        mongo_db=os.getenv("MONGO_DB", "orcapc_catalog").strip(),
        jwt_secret=os.getenv("JWT_SECRET", "").strip(),
        jwt_algorithm=algorithm,
        admin_api_key=os.getenv("ADMIN_API_KEY", "").strip(),
        cors_origins=_origins(),
        max_page_size=_positive_int("CATALOG_MAX_PAGE_SIZE", 100),
        max_batch_size=_positive_int("CATALOG_MAX_BATCH_SIZE", 100),
        max_search_length=_positive_int("CATALOG_MAX_SEARCH_LENGTH", 120),
        proxy_max_bytes=_positive_int("IMAGE_PROXY_MAX_BYTES", 5 * 1024 * 1024),
        proxy_connect_timeout=_positive_int("IMAGE_PROXY_CONNECT_TIMEOUT", 3),
        proxy_read_timeout=_positive_int("IMAGE_PROXY_READ_TIMEOUT", 10),
        ml_connect_timeout=_positive_int("ML_CONNECT_TIMEOUT", 3),
        ml_read_timeout=_positive_int("ML_READ_TIMEOUT", 10),
        refresh_cooldown_seconds=_nonnegative_int("REFRESH_COOLDOWN_SECONDS", 60),
    )
