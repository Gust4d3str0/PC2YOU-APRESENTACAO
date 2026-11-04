import json
import logging
from copy import deepcopy
from typing import Protocol

import httpx
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from .config import AISettings
from .diagnostics import log_failure
from .errors import AIError, AIInvalidResponseError


logger = logging.getLogger("pc2you.ai")


class AIProvider(Protocol):
    name: str

    def generate(self, *, system: str, context: dict, schema: dict) -> dict: ...


class GeminiProvider:
    """Only this module knows the official SDK, credentials and response envelope."""

    name = "gemini"

    def __init__(self, settings: AISettings, client=None):
        self.settings = settings
        self.client = client

    def generate(self, *, system: str, context: dict, schema: dict) -> dict:
        self.settings.ensure_available()
        try:
            config = types.GenerateContentConfig(
                system_instruction=system, temperature=0.2, max_output_tokens=8192,
                response_mime_type="application/json", response_json_schema=deepcopy(schema),
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            )
            if self.client is None:
                self.client = genai.Client(
                    api_key=self.settings.api_key, vertexai=False,
                    http_options=types.HttpOptions(
                        timeout=int(self.settings.timeout * 1000),
                        retry_options=types.HttpRetryOptions(attempts=1),
                    ),
                )
            response = self._call(self.client, context, config)
        except errors.APIError as exc:
            code = exc.code
            logger.warning("[AI] Provider request failed provider=gemini model=%s http_status=%s", self.settings.model, code)
            if code == 404:
                raise AIError("model_unavailable", "O modelo de IA configurado não está disponível. Revise GEMINI_MODEL.") from exc
            if code == 429:
                raise AIError("rate_limit", "A IA está ocupada. Aguarde um minuto e tente novamente.", 429) from exc
            if code in (408, 504):
                raise AIError("timeout", "A análise demorou mais que o esperado. Tente novamente.", 504) from exc
            if code in (401, 403):
                raise AIError("provider_auth", "A configuração de acesso à IA precisa ser revisada.") from exc
            if code == 503:
                raise AIError("overloaded", "A IA está temporariamente sobrecarregada. Tente novamente mais tarde.") from exc
            if code == 400:
                raise AIError("provider_request", "O provedor recusou a configuração da análise. Revise o modelo e o schema.") from exc
            raise AIError("unavailable", "A IA está temporariamente indisponível. Tente novamente mais tarde.") from exc
        except httpx.TimeoutException as exc:
            raise AIError("timeout", "A análise demorou mais que o esperado. Tente novamente.", 504) from exc
        except httpx.RequestError as exc:
            raise AIError("unavailable", "Não foi possível conectar à IA. Tente novamente mais tarde.") from exc
        except (ValidationError, ValueError) as exc:
            logger.warning("[AI] SDK configuration rejected provider=gemini model=%s error_type=%s", self.settings.model, type(exc).__name__)
            raise AIError("provider_configuration", "A configuração do SDK de IA precisa ser revisada.") from exc

        try:
            candidates = response.candidates
            if not candidates:
                return self._invalid("response.candidates", "empty_candidates", "non-empty array", "empty array")
            candidate = candidates[0]
            if candidate.finish_reason != "STOP":
                return self._invalid("response.finish_reason", "incomplete_response", "STOP", "other finish reason")
            parts = candidate.content.parts if candidate.content else None
            if not parts:
                return self._invalid("response.content.parts", "empty_content", "text parts", "empty")
            text = "".join(part.text for part in parts if isinstance(part.text, str) and not part.thought)
            if len(text.encode("utf-8")) > 131072:
                return self._invalid("response.text", "oversized_response", "at most 128 KiB", "oversized string")
            result = json.loads(text)
        except (ValueError, TypeError, AttributeError) as exc:
            issues = [{"field": "response.text", "category": "invalid_json", "expected": "JSON object", "received": "unparseable response"}]
            log_failure(self.settings, self.name, "parse", issues)
            raise AIInvalidResponseError(issues) from exc
        if not isinstance(result, dict):
            return self._invalid("$", "not_object", "object", type(result).__name__)
        return result

    def _call(self, client, context, config):
        return client.models.generate_content(
            model=self.settings.model,
            contents=json.dumps(context, ensure_ascii=False),
            config=config,
        )

    def _invalid(self, field, category, expected, received):
        issues = [{"field": field, "category": category, "expected": expected, "received": received}]
        log_failure(self.settings, self.name, "provider_response", issues)
        raise AIInvalidResponseError(issues)
