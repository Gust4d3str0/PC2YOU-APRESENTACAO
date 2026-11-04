import os
import re
from dataclasses import dataclass, field

from .errors import AIError


@dataclass(frozen=True)
class AISettings:
    enabled: bool = False
    api_key: str = field(default="", repr=False)
    model: str = "gemini-2.5-flash"
    timeout: float = 45
    cache_ttl: int = 300
    requests_per_minute: int = 10
    debug_validation: bool = False

    @classmethod
    def from_env(cls):
        try:
            config = cls(
                enabled=os.getenv("AI_ENABLED", "false").lower() == "true",
                api_key=os.getenv("GEMINI_API_KEY", "").strip(),
                model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
                timeout=float(os.getenv("AI_TIMEOUT_SECONDS", "45")),
                cache_ttl=int(os.getenv("AI_CACHE_TTL_SECONDS", "300")),
                requests_per_minute=int(os.getenv("AI_REQUESTS_PER_MINUTE", "10")),
                debug_validation=os.getenv("AI_DEBUG_VALIDATION", "false").lower() == "true",
            )
            if not (1 <= config.timeout <= 120 and 0 <= config.cache_ttl <= 3600
                    and 1 <= config.requests_per_minute <= 100
                    and re.fullmatch(r"[a-zA-Z0-9.-]{1,100}", config.model)):
                raise ValueError
            return config
        except ValueError as exc:
            raise AIError("configuration", "A configuração de IA precisa ser revisada.") from exc

    def ensure_available(self):
        if not self.enabled:
            raise AIError("disabled", "A análise por IA está desativada no momento.")
        if not self.api_key:
            raise AIError("missing_key", "A chave da IA ainda não foi configurada no servidor.")
