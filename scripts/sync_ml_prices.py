"""
Sincroniza preços e imagens do Mercado Livre para todos os componentes do catálogo.

Uso:
    python scripts/sync_ml_prices.py                     # sincroniza todos
    python scripts/sync_ml_prices.py rtx-4060            # sincroniza um componente
    python scripts/sync_ml_prices.py --api http://localhost:8002   # URL customizada

Pre-requisito: api-catalogo rodando (docker compose up api-catalogo)
"""

import sys
import time
import requests

DEFAULT_API = "http://localhost:8002"


def get_api_url() -> str:
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--api" and i < len(sys.argv) - 1:
            return sys.argv[i + 1]
    return DEFAULT_API


def sync_one(api_url: str, component_id: str) -> bool:
    try:
        resp = requests.post(
            f"{api_url}/components/{component_id}/sync-ml-price",
            timeout=20,
        )
        if resp.status_code == 200:
            data = resp.json()
            price = data.get("ml_price", {})
            print(f"  [OK] R$ {price.get('price', '?'):.2f} — {price.get('url', '')[:60]}")
            return True
        print(f"  [SEM RESULTADO] {resp.json().get('detail', resp.status_code)}")
        return False
    except Exception as e:
        print(f"  [ERRO] {e}")
        return False


def sync_all(api_url: str) -> None:
    try:
        components = requests.get(f"{api_url}/components", timeout=15).json()
    except Exception as e:
        print(f"Erro ao buscar componentes: {e}")
        sys.exit(1)

    total = len(components)
    ok, failed = 0, []

    print(f"Sincronizando {total} componentes com o Mercado Livre...\n")

    for i, comp in enumerate(components, 1):
        cid = comp["id"]
        print(f"[{i:03d}/{total}] {comp['name']}")
        if sync_one(api_url, cid):
            ok += 1
        else:
            failed.append(cid)
        if i < total:
            time.sleep(1.5)

    print(f"\n{'='*55}")
    print(f"Concluido: {ok} atualizados, {len(failed)} sem resultado")
    if failed:
        print("Sem resultado no ML:")
        for fid in failed:
            print(f"  - {fid}")


if __name__ == "__main__":
    api_url = get_api_url()
    args = [a for a in sys.argv[1:] if not a.startswith("--") and a != api_url]

    if args:
        component_id = args[0]
        print(f"Sincronizando {component_id}...")
        sync_one(api_url, component_id)
    else:
        sync_all(api_url)
