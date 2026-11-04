"""AI v2: real endpoint by default; --mock runs the actual route without network."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PAYLOAD = {
    "components": {"cpu": "ryzen-5-5600", "gpu": "rtx-3060", "motherboard": "b550m-am4-ddr4",
                   "ram": "ram-16gb-ddr4", "storage": ["ssd-nvme-1tb"], "psu": "fonte-650w", "case": "gabinete-atx"},
    "usage": ["gaming"], "resolution": "1080p", "refresh_rate": 144,
    "upgrade_budget": 4000, "include_promotions": True,
}


def mock_app():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "api-orcamentos"))
    import ai_routes
    from ai import AIService
    from ai.config import AISettings
    from main import app

    def piece(cid, category, name, specs=None, compat=None):
        return {"id": cid, "category": category, "name": name, "technical_specs": specs or {},
                "compatibility": compat or {}, "prices": [], "benchmark": {"gaming_score": 50}}

    current = [
        piece("ryzen-5-5600", "cpu", "AMD Ryzen 5 5600", {"cores": 6}, {"socket": "AM4"}),
        piece("rtx-3060", "gpu", "GeForce RTX 3060", {"memory": "12GB", "length_mm": 200}, {"min_psu_watts": 550}),
        piece("b550m-am4-ddr4", "motherboard", "Placa-mãe B550M AM4 DDR4", {"memory_slots": 4, "max_memory_gb": 128},
              {"socket": "AM4", "memory_type": "DDR4", "form_factor": "ATX"}),
        piece("ram-16gb-ddr4", "ram", "RAM 16GB DDR4", {"capacity": "16GB"}, {"memory_type": "DDR4"}),
        piece("ssd-nvme-1tb", "storage", "SSD NVMe 1TB"),
        piece("fonte-650w", "psu", "Fonte 650W", {"wattage": 650}),
        piece("gabinete-atx", "case", "Gabinete ATX", {}, {"supported_form_factors": ["ATX"], "max_gpu_length_mm": 350}),
    ]
    now = datetime.now(timezone.utc)
    candidate = piece("rtx-5070", "gpu", "GeForce RTX 5070", {"memory": "12GB", "length_mm": 250}, {"min_psu_watts": 650})
    candidate["benchmark"]["gaming_score"] = 80
    candidate["prices"] = [{"price": 3899.9, "store": "Catálogo simulado", "source": "mercado_livre",
                            "title": "GeForce RTX 5070 12GB",
                            "availability": "Disponível", "last_update": now.isoformat()}]

    class Catalog:
        def search_components(self, category, query):
            return [c for c in current if c["category"] == category and query in {c["id"], c["name"]}]

        def list_components(self, category):
            return [c for c in current + [candidate] if c["category"] == category]

    class Promotions:
        def recent(self, timestamp):
            return [{"_id": "demo-promotion", "status": "parsed", "created_at": now,
                     "product": {"name": "GeForce RTX 5070 12GB", "component_id": "rtx-5070", "component_type": "gpu"},
                     "offer": {"price": 3599.9, "store": "Loja de demonstração", "coupon": "DEMO10", "url": None}}], True

    class Provider:
        name = "demo-mock"

        def generate(self, **kwargs):
            return {"summary": "Simulação: há uma opção do catálogo para avaliar.",
                    "recommended_upgrades": [{"priority": 1, "candidate_id": "rtx-5070", "component_type": "gpu",
                                               "reason": "Avalie a prioridade gráfica conforme seus jogos.",
                                               "confidence": "medium", "budget_relevance": "within_budget"}],
                    "buy_now_opportunities": [], "warnings": ["Esta resposta é uma simulação, sem consulta ao Gemini."],
                    "final_recommendation": "Confirme requisitos e dados da peça antes de decidir."}

    service = AIService(AISettings(enabled=True, api_key="mock-only"), Provider())
    ai_routes.get_ai_service = lambda: service
    ai_routes.get_promotion_source = Promotions
    app.dependency_overrides[ai_routes.get_ai_catalog] = Catalog
    return app


def display(data):
    print(f"Provider: {data['metadata']['provider']}")
    for item in data["recommendations"]:
        offer = item["promotion"] or {}
        price = item["price"]
        print(f"\nUpgrade recomendado: {item['component']['name']}")
        print(f"Preço: {price['value'] if price['value'] is not None else 'não disponível'}")
        print(f"Fonte do preço: {price['source']} (verificado: {'sim' if price['verified'] else 'não'})")
        print(f"Promoção: {'sim' if offer else 'não'}")
        print(f"Loja: {offer.get('store') or price.get('store') or 'não informada'}")
        print(f"Cupom: {offer.get('coupon') or 'não informado'}")
        print(f"URL disponível: {'sim' if offer.get('url') else 'não'}")
        print(f"Compatibilidade: {item['compatibility']['status']}")
    if not data["recommendations"]:
        print("Nenhum modelo foi selecionado; confira os dados necessários e as opções do catálogo.")
    for warning in data["warnings"]:
        print(f"Aviso: {warning}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8003/ai/recommend-upgrades")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--without-promotions", action="store_true")
    args = parser.parse_args()
    payload = {**PAYLOAD, "include_promotions": not args.without_promotions}
    try:
        if args.mock:
            from fastapi.testclient import TestClient
            print("SIMULAÇÃO SEM REDE — preços e promoções fictícios; nenhuma URL foi inventada.")
            response = TestClient(mock_app()).post("/ai/recommend-upgrades", json=payload)
            if response.status_code != 200:
                print(f"HTTP {response.status_code}: {response.json().get('detail', {}).get('code', 'error')}")
                return 1
            data = response.json()
        else:
            request = Request(args.url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(request, timeout=130) as response:
                data = json.load(response)
        display(data)
        return 0
    except HTTPError as exc:
        body = json.load(exc)
        print(f"HTTP {exc.code}: {body.get('detail', {}).get('code', 'error')}", file=sys.stderr)
    except (URLError, TimeoutError):
        print("API indisponível ou timeout. Confira os serviços.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
