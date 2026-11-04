import json
import logging
import re
import time
import uuid
from contextvars import ContextVar

from fastapi import Request


SERVICE_NAME = "api-orcamentos"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
logger = logging.getLogger(SERVICE_NAME)
logger.setLevel(logging.INFO)


def current_request_id() -> str | None:
    return request_id_var.get()


async def request_context_middleware(request: Request, call_next):
    incoming = request.headers.get("X-Request-ID", "")
    request_id = incoming if REQUEST_ID_PATTERN.fullmatch(incoming) else str(uuid.uuid4())
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(json.dumps({
            "service": SERVICE_NAME,
            "method": request.method,
            "path": request.url.path,
            "status": status_code,
            "duration_ms": duration_ms,
            "request_id": request_id,
        }, ensure_ascii=False))
        request_id_var.reset(token)
