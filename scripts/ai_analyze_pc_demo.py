"""AI v1 HTTP demo. Real API by default; --mock is explicit and never calls Gemini."""

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PAYLOAD = {
    "components": {
        "cpu": "Ryzen 5 5600", "gpu": "RTX 3060 12 GB",
        "motherboard": "Placa-mãe B550M AM4 DDR4", "ram": "Kingston Fury Beast 16GB DDR4 3200MHz",
        "storage": ["SSD NVMe 1TB"], "psu": "Fonte 650W",
    },
    "usage": ["gaming", "programming"], "resolution": "1080p", "refresh_rate": 144,
    "games": ["Valorant", "Cyberpunk 2077"], "upgrade_budget": 2000,
}


def mock_app():
    # Uses the real route, enrichment, deterministic engine and output validation.
    # Only catalog transport and AI provider are replaced. No fallback exists in production.
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "api-orcamentos"))
    import ai_routes
    from ai import AIService
    from ai.config import AISettings
    from main import app

    class DemoCatalog:
        def search_components(self, category, query):
            items = [
                {"id": "ryzen-5-5600", "name": "AMD Ryzen 5 5600", "category": "cpu",
                 "technical_specs": {"cores": 6, "threads": 12, "tdp_watts": 65}, "compatibility": {"socket": "AM4"}},
                {"id": "rtx-3060", "name": "GeForce RTX 3060", "category": "gpu",
                 "technical_specs": {"memory": "12GB GDDR6", "length_mm": 200}, "compatibility": {"min_psu_watts": 550}},
                {"id": "b550m-am4-ddr4", "name": "Placa-mãe B550M AM4 DDR4", "category": "motherboard",
                 "technical_specs": {"memory_slots": 4}, "compatibility": {"socket": "AM4", "memory_type": "DDR4"}},
                {"id": "ram-16gb-ddr4", "name": "Kingston Fury Beast 16GB DDR4 3200MHz", "category": "ram",
                 "technical_specs": {"capacity": "16GB"}, "compatibility": {"memory_type": "DDR4"}},
                {"id": "fonte-650w", "name": "Fonte 650W", "category": "psu", "technical_specs": {"wattage": 650}},
            ]
            return [item for item in items if item["category"] == category]

        def list_components(self, category):
            return []

    class DemoProvider:
        name = "demo-mock"

        def generate(self, **kwargs):
            return {
                "summary": "Esta resposta simulada demonstra a análise estruturada para jogos em 1080p.",
                "overall_rating": "attention",
                "balance": {"status": "insufficient_data", "explanation": "Confirme os dados ausentes para avaliar melhor o conjunto."},
                "primary_limit": {"component": "gpu", "confidence": "low", "explanation": "A placa de vídeo é uma oportunidade possível conforme o jogo e os ajustes gráficos."},
                "strengths": ["O processador possui especificações identificadas no catálogo de demonstração."],
                "weaknesses": ["Ainda há dados de compatibilidade a confirmar."],
                "upgrade_priorities": [{"priority": 1, "component_type": "gpu", "candidate_id": None,
                                        "reason": "Avalie a carga gráfica nos jogos que você utiliza.",
                                        "expected_benefit": "Mais margem para qualidade gráfica, conforme o cenário.",
                                        "budget_relevance": "save_budget"}],
                "warnings": ["Demonstração simulada; não é uma análise feita pelo Gemini."],
                "missing_information": [], "final_recommendation": "Confirme a fonte e a compatibilidade antes de escolher uma peça.",
            }

    service = AIService(AISettings(enabled=True, api_key="demo-only-no-real-key"), DemoProvider())
    ai_routes.get_ai_service = lambda: service
    app.dependency_overrides[ai_routes.get_ai_catalog] = DemoCatalog
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8003/ai/analyze-pc")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true", help="Run the real endpoint in-process with a simulated provider/catalog")
    mode.add_argument("--serve-mock", action="store_true", help="Serve an explicitly simulated demo at 127.0.0.1:8003")
    args = parser.parse_args()
    if args.serve_mock:
        import uvicorn
        print("DEMONSTRAÇÃO SIMULADA. Não usa Gemini nem catálogo real.", flush=True)
        uvicorn.run(mock_app(), host="127.0.0.1", port=8003)
        return 0
    if args.mock:
        from fastapi.testclient import TestClient
        response = TestClient(mock_app()).post("/ai/analyze-pc", json=PAYLOAD)
        print(json.dumps(response.json(), ensure_ascii=False, indent=2))
        return 0 if response.status_code == 200 else 1
    try:
        request = Request(args.url, data=json.dumps(PAYLOAD).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=130) as response:
            print(json.dumps(json.load(response), ensure_ascii=False, indent=2))
        return 0
    except HTTPError as exc:
        print(f"API retornou HTTP {exc.code}: {exc.read().decode('utf-8')}", file=sys.stderr)
    except (URLError, TimeoutError):
        print("Não foi possível acessar a API. Confira os serviços e a URL.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
