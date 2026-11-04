import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import quote_plus


def _csv(name: str, default: str) -> tuple[str, ...]:
    values = tuple(value.strip() for value in os.getenv(name, default).split(",") if value.strip())
    if not values or "*" in values:
        raise RuntimeError(f"{name} deve listar origens explícitas")
    return values


@dataclass(frozen=True)
class Settings:
    database_url: str
    catalog_api_url: str
    catalog_connect_timeout: float
    catalog_read_timeout: float
    catalog_retries: int
    jwt_secret: str | None
    jwt_algorithm: str
    jwt_audience: str | None
    cors_origins: tuple[str, ...]


@lru_cache
def get_settings() -> Settings:
    explicit_url = os.getenv("DATABASE_URL")
    if explicit_url:
        database_url = explicit_url
    else:
        user = quote_plus(os.getenv("POSTGRES_USER", "orcapc_user"))
        password = quote_plus(os.getenv("POSTGRES_PASSWORD", "orcapc_password"))
        database = quote_plus(os.getenv("POSTGRES_DB", "orcapc_db"))
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        database_url = f"postgresql://{user}:{password}@{host}:{port}/{database}"

    audience = os.getenv("JWT_AUDIENCE") or None
    jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256").strip().upper()
    if jwt_algorithm not in {"HS256", "HS384", "HS512"}:
        raise RuntimeError("JWT_ALGORITHM deve usar HS256, HS384 ou HS512")
    try:
        catalog_connect_timeout = float(os.getenv("CATALOG_CONNECT_TIMEOUT", "2"))
        catalog_read_timeout = float(os.getenv("CATALOG_READ_TIMEOUT", "8"))
        catalog_retries = int(os.getenv("CATALOG_RETRIES", "2"))
    except ValueError as exc:
        raise RuntimeError("Configuração numérica do catálogo inválida") from exc
    if catalog_connect_timeout <= 0 or catalog_read_timeout <= 0 or catalog_retries < 0:
        raise RuntimeError("Timeouts devem ser positivos e retries não pode ser negativo")
    return Settings(
        database_url=database_url,
        catalog_api_url=os.getenv("CATALOG_API_URL", "http://api-catalogo:8000").rstrip("/"),
        catalog_connect_timeout=catalog_connect_timeout,
        catalog_read_timeout=catalog_read_timeout,
        catalog_retries=catalog_retries,
        jwt_secret=(os.getenv("JWT_SECRET") or "").strip() or None,
        jwt_algorithm=jwt_algorithm,
        jwt_audience=audience,
        cors_origins=_csv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://frontend:5173",
        ),
    )
