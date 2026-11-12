from typing import Any
import re
from urllib.parse import quote

import requests
from fastapi import HTTPException
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from settings import Settings, get_settings
from request_context import current_request_id


# Upgrade suggestions are optional; they must never consume the analysis time budget.
OPTIONAL_READ_TIMEOUT = 6


class CatalogClient:
    def __init__(self, settings: Settings | None = None, session: requests.Session | None = None):
        self.settings = settings or get_settings()
        self.base_url = self.settings.catalog_api_url
        self.timeout = (
            self.settings.catalog_connect_timeout,
            self.settings.catalog_read_timeout,
        )
        self.session = session or requests.Session()
        retry = Retry(
            total=self.settings.catalog_retries,
            connect=self.settings.catalog_retries,
            read=self.settings.catalog_retries,
            status=self.settings.catalog_retries,
            status_forcelist=(429, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            backoff_factor=0.2,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        request_id = current_request_id()
        if request_id:
            headers = dict(kwargs.pop("headers", {}))
            headers["X-Request-ID"] = request_id
            kwargs["headers"] = headers
        timeout = kwargs.pop("timeout", self.timeout)
        try:
            return self.session.request(
                method,
                f"{self.base_url}{path}",
                timeout=timeout,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise HTTPException(status_code=503, detail="Catálogo temporariamente indisponível") from exc

    @staticmethod
    def _json(response: requests.Response) -> Any:
        try:
            return response.json()
        except (requests.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=503, detail="Resposta inválida do catálogo") from exc

    def _checked_json(self, response: requests.Response) -> Any:
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Peça não encontrada no catálogo")
        if response.status_code >= 500:
            raise HTTPException(status_code=503, detail="Catálogo temporariamente indisponível")
        if response.status_code >= 400:
            raise HTTPException(status_code=503, detail="Falha ao consultar o catálogo")
        return self._json(response)

    def health(self) -> None:
        response = self._request("GET", "/health/ready")
        body = self._checked_json(response)
        if not isinstance(body, dict) or body.get("status") not in {"ok", "ready"}:
            raise HTTPException(status_code=503, detail="Catálogo não está pronto")

    def get_component(self, component_id: str) -> dict:
        body = self._checked_json(self._request("GET", f"/components/{component_id}"))
        if not isinstance(body, dict):
            raise HTTPException(status_code=503, detail="Resposta inválida do catálogo")
        return body

    def get_components(self, component_ids: list[str]) -> list[dict]:
        response = self._request(
            "POST",
            "/components/batch",
            json={"component_ids": component_ids},
        )
        if response.status_code in {404, 405}:
            return [self.get_component(component_id) for component_id in component_ids]

        body = self._checked_json(response)
        if isinstance(body, dict):
            body = body.get("components")
        if not isinstance(body, list) or any(not isinstance(item, dict) for item in body):
            raise HTTPException(status_code=503, detail="Resposta inválida do catálogo")
        return body

    def list_components(self, category: str | None = None) -> list[dict]:
        params = {"category": category} if category else None
        body = self._checked_json(self._request("GET", "/components", params=params))
        if not isinstance(body, list) or any(not isinstance(item, dict) for item in body):
            raise HTTPException(status_code=503, detail="Resposta inválida do catálogo")
        return body

    def search_components(self, category: str, query: str) -> list[dict]:
        if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)+", query):
            response = self._request("GET", f"/components/{quote(query, safe='')}")
            if response.status_code != 404:
                item = self._checked_json(response)
                if not isinstance(item, dict):
                    raise HTTPException(status_code=503, detail="Resposta inválida do catálogo")
                return [item]
        body = self._checked_json(self._request(
            "GET", "/components", params={"category": category, "q": query},
        ))
        if not isinstance(body, list) or any(not isinstance(item, dict) for item in body):
            raise HTTPException(status_code=503, detail="Resposta inválida do catálogo")
        return body

    def resolve_components(self, category: str, query: str) -> list[dict]:
        body = self._checked_json(self._request('GET', '/components/resolve', params={'category': category, 'q': query}))
        if not isinstance(body, list) or len(body) > 32 or any(not isinstance(item, dict) for item in body):
            raise HTTPException(status_code=503, detail='Resposta inválida do resolver do catálogo')
        return body

    def human_candidates(self, category: str, query: str) -> dict:
        body = self._checked_json(self._request('GET', '/components/resolve-human', params={'category': category, 'q': query}))
        if (not isinstance(body, dict) or not isinstance(body.get('candidates'), list)
                or len(body['candidates']) > 32 or any(not isinstance(r, dict) for r in body['candidates'])
                or not isinstance(body.get('overflow'), bool) or (body.get('family') is not None and not isinstance(body['family'], dict))):
            raise HTTPException(status_code=503, detail='Resposta inválida do resolver técnico')
        return body

    def upgrade_candidates(self, category: str, limit: int = 24) -> list[dict]:
        body = self._checked_json(self._request('GET', '/components', params={'category': category, 'limit': min(limit, 24), 'technical_only': True},
                                                       timeout=(self.timeout[0], min(self.timeout[1], OPTIONAL_READ_TIMEOUT))))
        if not isinstance(body, list) or len(body) > 24 or any(not isinstance(item, dict) for item in body):
            raise HTTPException(status_code=503, detail='Resposta inválida do catálogo')
        return body


catalog_client = CatalogClient()
