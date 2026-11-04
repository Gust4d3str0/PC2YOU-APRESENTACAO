import logging


class SecretFormatter(logging.Formatter):
    def __init__(self, secrets=()):
        super().__init__("%(asctime)s [Telegram] %(message)s")
        self.secrets = tuple(secret for secret in secrets if secret)

    def format(self, record):
        value = super().format(record)
        for secret in self.secrets:
            value = value.replace(secret, "[REDACTED]")
        return value


def configure_logging(settings):
    logger = logging.getLogger("pc2you.telegram")
    handler = logging.StreamHandler()
    handler.setFormatter(SecretFormatter((settings.api_hash, settings.phone, settings.bot_token, settings.mongo_uri)))
    logger.handlers[:] = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    # HTTP clients podem incluir a URL da Bot API (e portanto o token) nos logs.
    for name in ("telethon", "telegram", "httpx", "httpcore", "pymongo"):
        logging.getLogger(name).setLevel(logging.CRITICAL + 1)
    return logger
