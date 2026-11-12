import hashlib
import json
import threading
import time
from collections import OrderedDict, deque
from copy import deepcopy

from pydantic import ValidationError

from .config import AISettings
from .errors import AIError, AIInvalidResponseError, ContractViolation
from .contract import analysis_schema, budget_relevance_values, normalize_enums
from .diagnostics import log_failure, pydantic_issues
from .prompts import PROMPT_VERSION, SYSTEM_PROMPT
from .provider import AIProvider, GeminiProvider
from .schemas import AnalyzePCResponse, PCAnalysis
from .prose import validate_prose
from .presentation import unique_messages
from .assessment import fallback_analysis, recognized, upgrade_assessment


# Availability failures of the external provider. Invalid/unsafe model output is still rejected, never masked.
FALLBACK_CODES = {"timeout", "overloaded", "unavailable"}


class AIService:
    def __init__(self, settings: AISettings | None = None, provider: AIProvider | None = None, clock=time.monotonic):
        self.settings = settings or AISettings.from_env()
        self.provider = provider or GeminiProvider(self.settings)
        self.clock = clock
        self._cache = OrderedDict()
        self._calls = deque()
        self._lock = threading.Lock()

    def ensure_available(self):
        self.settings.ensure_available()

    def run_cached(self, context, version, operation, private_context=None):
        self.ensure_available()
        key = hashlib.sha256(json.dumps(
            {"context": context, "private": private_context, "model": self.settings.model, "prompt": version},
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        ).encode()).hexdigest()
        # One call in flight per worker; duplicates cannot spend a second request.
        if not self._lock.acquire(blocking=False):
            raise AIError("busy", "Uma análise já está em andamento. Aguarde e tente novamente.", 429)
        try:
            now = self.clock()
            expired = [k for k, (expires, _) in self._cache.items() if expires <= now]
            for k in expired:
                del self._cache[k]
            if key in self._cache:
                result = deepcopy(self._cache[key][1])
                result.metadata.cached = True
                return result
            while self._calls and self._calls[0] <= now - 60:
                self._calls.popleft()
            if len(self._calls) >= self.settings.requests_per_minute:
                raise AIError("rate_limit", "O limite de análises foi atingido. Aguarde um minuto.", 429)
            self._calls.append(now)
            result = operation()
            if self.settings.cache_ttl and getattr(getattr(result, 'metadata', None), 'analysis_source', 'gemini') == 'gemini':
                self._cache[key] = (self.clock() + self.settings.cache_ttl, deepcopy(result))
                while len(self._cache) > 128:
                    self._cache.popitem(last=False)
            return result
        finally:
            self._lock.release()

    def analyze_pc(self, context: dict) -> AnalyzePCResponse:
        return self.run_cached(context, PROMPT_VERSION, lambda: self._analyze_pc(context))

    def _analyze_pc(self, context):
        schema = analysis_schema(context)
        try:
            analysis, selected = self._model_analysis(context, schema)
            source, reason = "gemini", None
        except AIError as exc:
            if exc.code not in FALLBACK_CODES:
                raise
            # The provider is an external dependency. Verified backend facts are still worth showing,
            # clearly labelled as NOT a model answer.
            trusted = context["trusted_context"]
            analysis = PCAnalysis.model_validate(fallback_analysis(trusted, context["user_context"]))
            selected, source, reason = [], "deterministic_fallback", exc.code
        trusted = context["trusted_context"]
        missing = trusted["missing_information"]
        ready = trusted["analysis_readiness"]
        if ready["status"] == "sufficient" and analysis.primary_limit and analysis.primary_limit.component == "unknown":
            analysis.primary_limit = None  # "unknown" never stands for "no data": nothing confirmed as a limit.
        limit = analysis.primary_limit
        # Confidence reflects the evidence behind THIS claim, not unrelated pending rules.
        if limit and (ready["status"] != "sufficient" or not any(
                recognized(item) for item in trusted["build"] if item["category"] == limit.component)):
            limit.confidence = "low"
        analysis.missing_information = unique_messages(missing)[:15]
        # Pending physical rules live in the compatibility block, not in the alerts card.
        backend_warnings = [w for w in trusted["compatibility"]["warnings"] if not w.startswith("Compatibilidade parcial")]
        analysis.warnings = unique_messages(backend_warnings + analysis.warnings)[:12]
        if trusted["compatibility"]["issues"]:
            analysis.overall_rating = "attention"
            analysis.balance.status = "attention"
        assessment = upgrade_assessment(trusted, analysis.upgrade_priorities)
        result = AnalyzePCResponse(
            analysis=analysis, compatibility=trusted["compatibility"],
            compatibility_notes=unique_messages(trusted["compatibility"]["issues"] + trusted["compatibility"]["warnings"]),
            components=trusted["build"], recommended_candidates=selected,
            upgrade_budget=context["user_context"]["upgrade_budget"],
            readiness=ready, upgrade_assessment=assessment,
            metadata={"provider": self.provider.name if source == "gemini" else "backend", "model": self.settings.model if source == "gemini" else "deterministic",
                      "catalog_matches": sum(item["source"] == "catalog" for item in trusted["build"]),
                      "technical_matches": sum(item['source'] in {'catalog', 'derived'} for item in trusted['build']),
                      "derived_matches": sum(item['source'] == 'derived' for item in trusted['build']),
                      "compatibility_checked": True, "cached": False, "prompt_version": PROMPT_VERSION,
                      "analysis_source": source, "fallback_reason": reason},
        )
        return result

    def _model_analysis(self, context, schema):
        raw = self.provider.generate(system=SYSTEM_PROMPT, context=context, schema=schema)
        try:
            analysis = PCAnalysis.model_validate(normalize_enums(raw, schema))
        except ValidationError as exc:
            issues = pydantic_issues(exc, schema)
            log_failure(self.settings, self.provider.name, "pydantic", issues, raw, schema)
            raise AIInvalidResponseError(issues) from exc
        try:
            selected = self._validate_analysis(analysis, context)
        except ContractViolation as exc:
            issues = [exc.issue()]
            log_failure(self.settings, self.provider.name, "semantic", issues, raw, schema)
            raise AIInvalidResponseError(issues) from exc
        return analysis, selected

    @staticmethod
    def _validate_analysis(analysis, context):
        trusted = context["trusted_context"]
        candidates = {item["component_id"]: item for item in trusted["upgrade_candidates"]}
        budget = context["user_context"]["upgrade_budget"]
        selected = []
        if trusted["analysis_readiness"]["status"] == "sufficient" and "insufficient_data" in (analysis.overall_rating, analysis.balance.status):
            raise ContractViolation("overall_rating", "insufficiency_not_supported", "sufficiency is decided by the backend", "string enum")
        for index, priority in enumerate(analysis.upgrade_priorities):
            candidate = candidates.get(priority.candidate_id)
            if priority.candidate_id and (not candidate or candidate["component_type"] != priority.component_type):
                raise ContractViolation(f"upgrade_priorities.{index}.candidate_id", "candidate_not_allowed", "catalog candidate of same component type", "string")
            if candidate:
                selected.append(candidate)
            allowed = budget_relevance_values(candidate, budget)
            if priority.budget_relevance not in allowed:
                raise ContractViolation(f"upgrade_priorities.{index}.budget_relevance", "unsupported_budget_claim", "|".join(allowed), "string enum")
        if budget is not None and sum(item["price"] or 0 for item in selected) > budget:
            raise ContractViolation("upgrade_priorities", "budget_exceeded", "combined catalog prices within budget", "array")
        # Free prose is deliberately type-level only. Models and prices are rendered from
        # backend candidate records, never from model-written names or monetary text.
        def texts(value, path=""):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key not in {"candidate_id", "priority"}:
                        yield from texts(item, f"{path}.{key}".strip("."))
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    yield from texts(item, f"{path}.{index}")
            elif isinstance(value, str):
                yield path, value
        for path, value in texts(analysis.model_dump()):
            validate_prose(value, path, context, selected)
        return selected
