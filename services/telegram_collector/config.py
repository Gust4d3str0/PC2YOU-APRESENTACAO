import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ConfigurationError(ValueError):
    pass


def parse_allowed_chats(raw: str) -> frozenset[int]:
    try:
        ids = frozenset(int(part.strip()) for part in raw.split(",") if part.strip())
    except ValueError:
        raise ConfigurationError("TELEGRAM_ALLOWED_CHATS deve conter IDs numéricos separados por vírgula.") from None
    if any(chat_id >= 0 for chat_id in ids):
        raise ConfigurationError("TELEGRAM_ALLOWED_CHATS aceita somente IDs negativos de grupos/canais.")
    return ids


@dataclass(frozen=True)
class Settings:
    mongo_uri: str = field(default="mongodb://localhost:27017", repr=False)
    mongo_db: str = "orcapc_catalog"
    api_id: int | None = None
    api_hash: str = field(default="", repr=False)
    phone: str = field(default="", repr=False)
    bot_token: str = field(default="", repr=False)
    allowed_chats: frozenset[int] = frozenset()
    session_path: Path = PROJECT_ROOT / "services/telegram_collector/data/pc2you"
    history_limit: int = 100
    allowed_users: frozenset[int] = frozenset()
    alert_dedup_hours: int = 6
    notification_poll_seconds: int = 10

    def require_account(self, *, authentication: bool = False) -> None:
        if not self.api_id or self.api_id <= 0 or not self.api_hash:
            raise ConfigurationError("Configure TELEGRAM_API_ID e TELEGRAM_API_HASH.")
        if authentication and not self.phone:
            raise ConfigurationError("Configure TELEGRAM_PHONE para autenticar a conta.")

    def require_sources(self) -> None:
        if not self.allowed_chats:
            raise ConfigurationError("Configure TELEGRAM_ALLOWED_CHATS antes de coletar ou importar.")


def load_settings() -> Settings:
    # Caminho estável mesmo quando o processo é iniciado fora da raiz.
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    try:
        api_id = int(os.getenv("TELEGRAM_API_ID", "").strip() or "0") or None
        limit = int(os.getenv("TELEGRAM_HISTORY_LIMIT", "100"))
        dedup_hours = int(os.getenv("TELEGRAM_ALERT_DEDUP_HOURS", "6"))
        poll_seconds = int(os.getenv("TELEGRAM_NOTIFICATION_POLL_SECONDS", "10"))
        allowed_users = frozenset(int(value.strip()) for value in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",") if value.strip())
    except ValueError:
        raise ConfigurationError("As configurações numéricas do Telegram devem conter inteiros válidos.") from None
    if limit <= 0:
        raise ConfigurationError("TELEGRAM_HISTORY_LIMIT deve ser maior que zero.")
    if dedup_hours <= 0 or poll_seconds <= 0 or any(user_id <= 0 for user_id in allowed_users):
        raise ConfigurationError("IDs de usuários, intervalo de notificações e janela de deduplicação devem ser positivos.")
    session = Path(os.getenv("TELEGRAM_SESSION_PATH", "services/telegram_collector/data/pc2you"))
    if not session.is_absolute():
        session = PROJECT_ROOT / session
    return Settings(
        mongo_uri=os.getenv("MONGO_URI", "mongodb://localhost:27017").strip(),
        mongo_db=os.getenv("MONGO_DB", "orcapc_catalog").strip(),
        api_id=api_id,
        api_hash=os.getenv("TELEGRAM_API_HASH", "").strip(),
        phone=os.getenv("TELEGRAM_PHONE", "").strip(),
        bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        allowed_chats=parse_allowed_chats(os.getenv("TELEGRAM_ALLOWED_CHATS", "")),
        session_path=session,
        history_limit=limit,
        allowed_users=allowed_users,
        alert_dedup_hours=dedup_hours,
        notification_poll_seconds=poll_seconds,
    )
