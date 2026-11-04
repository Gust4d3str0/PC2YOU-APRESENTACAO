"""
PC2YOU — Sync seguro de preços reais e imagens reais.

Não altera seed.py, não roda /seed, não limpa banco e não muda nomes/specs.
Ele só chama o endpoint existente:

    POST /components/{id}/refresh-real-prices

Uso:
    python scripts/sync_safe_real_prices_images.py
    python scripts/sync_safe_real_prices_images.py --category ram
    python scripts/sync_safe_real_prices_images.py --category storage
    python scripts/sync_safe_real_prices_images.py --only-missing
    python scripts/sync_safe_real_prices_images.py --dry-run
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path


DEFAULT_API_URL = "http://localhost:8002"
REPORT_FILE = Path(__file__).resolve().parents[1] / "reports/sync_safe_real_prices_images_report.json"


def request_json(url, method="GET", timeout=90):
    req = urllib.request.Request(
        url,
        method=method,
        headers={"Accept": "application/json", "User-Agent": "PC2YOU-Safe-Sync/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            return error.code, json.loads(body)
        except Exception:
            return error.code, {"error": body}
    except Exception as error:
        return 0, {"error": str(error)}


def get_components(api_url):
    status, data = request_json(f"{api_url}/components", timeout=30)
    if status != 200:
        raise RuntimeError(f"Erro ao buscar componentes: HTTP {status} — {data}")
    if not isinstance(data, list):
        raise RuntimeError(f"Resposta inesperada em /components: {data}")
    return data


def get_component(api_url, component_id):
    status, data = request_json(f"{api_url}/components/{component_id}", timeout=30)
    return data if status == 200 and isinstance(data, dict) else {}


def has_real_data(component):
    if component.get("real_image"):
        return True
    for price in component.get("prices") or []:
        if price.get("source") == "mercado_livre" or price.get("store") == "Mercado Livre":
            return True
    return False


def refresh_component(api_url, component_id):
    return request_json(
        f"{api_url}/components/{component_id}/refresh-real-prices",
        method="POST",
        timeout=90,
    )


def yes_no(value):
    return "sim" if value else "não"


def parse_args():
    parser = argparse.ArgumentParser(description="Atualiza preços reais e imagens reais do PC2YOU com segurança.")
    parser.add_argument("--api", default=DEFAULT_API_URL, help="URL da API catálogo.")
    parser.add_argument("--category", default=None, help="Filtra por categoria: ram, storage, gpu, cpu, cooler etc.")
    parser.add_argument("--only-missing", action="store_true", help="Atualiza só componentes sem preço real e sem imagem real.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria atualizado, mas não chama refresh.")
    parser.add_argument("--delay", type=float, default=1.2, help="Intervalo entre chamadas.")
    parser.add_argument("--limit", type=int, default=0, help="Limita quantidade processada. 0 = sem limite.")
    return parser.parse_args()


def main():
    args = parse_args()
    api_url = args.api.rstrip("/")

    print("=" * 78)
    print("PC2YOU — Sync seguro de preços reais e imagens reais")
    print("=" * 78)
    print(f"API: {api_url}")
    print(f"Categoria: {args.category or 'todas'}")
    print(f"Apenas sem dados reais: {yes_no(args.only_missing)}")
    print(f"Dry-run: {yes_no(args.dry_run)}")
    print("=" * 78)

    components = get_components(api_url)

    if args.category:
        components = [c for c in components if c.get("category") == args.category]

    if args.only_missing:
        components = [c for c in components if not has_real_data(c)]

    if args.limit and args.limit > 0:
        components = components[: args.limit]

    total = len(components)
    report = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "finished_at": None,
        "api_url": api_url,
        "category": args.category,
        "only_missing": args.only_missing,
        "dry_run": args.dry_run,
        "total_selected": total,
        "processed": 0,
        "success_http": 0,
        "with_real_prices": 0,
        "with_real_image": 0,
        "updated_external": 0,
        "fallback": 0,
        "failed": 0,
        "items": [],
    }

    print(f"Componentes selecionados: {total}\n")

    for index, component in enumerate(components, start=1):
        component_id = component.get("id")
        name = component.get("name", component_id)
        category = component.get("category", "?")

        print(f"[{index:03d}/{total}] {component_id} — {name} ({category})")

        if not component_id:
            report["failed"] += 1
            report["items"].append({"id": None, "name": name, "error": "Componente sem ID."})
            print("   ERRO: componente sem ID.")
            continue

        if args.dry_run:
            item = {
                "id": component_id,
                "name": name,
                "category": category,
                "dry_run": True,
                "already_has_real_data": has_real_data(component),
            }
            report["items"].append(item)
            report["processed"] += 1
            print("   DRY-RUN: não atualizou.")
            continue

        status, data = refresh_component(api_url, component_id)
        data = data if isinstance(data, dict) else {}

        updated_component = get_component(api_url, component_id)
        summary = data.get("summary") or {}
        real_prices_count = summary.get("real_prices_count", 0)
        if not isinstance(real_prices_count, (int, float)):
            real_prices_count = 0

        real_image = updated_component.get("real_image")
        item = {
            "id": component_id,
            "name": name,
            "category": category,
            "status_code": status,
            "updated_external": bool(data.get("updated_external")),
            "offers_found": data.get("offers_found", 0),
            "offers_used": data.get("offers_used", 0),
            "real_prices_count": real_prices_count,
            "has_real_image": bool(real_image),
            "real_image": real_image,
            "image_source": updated_component.get("image_source"),
            "external_error": data.get("external_error"),
            "sources": summary.get("sources", []),
            "best_offer": summary.get("best_offer"),
            "real_best_offer": summary.get("real_best_offer"),
        }

        report["items"].append(item)
        report["processed"] += 1

        if status == 200:
            report["success_http"] += 1
        else:
            report["failed"] += 1

        if item["updated_external"]:
            report["updated_external"] += 1
        else:
            report["fallback"] += 1

        if item["real_prices_count"] > 0:
            report["with_real_prices"] += 1

        if item["has_real_image"]:
            report["with_real_image"] += 1

        print(
            f"   OK | HTTP {status}"
            f" | preços reais: {item['real_prices_count']}"
            f" | imagem real: {yes_no(item['has_real_image'])}"
            f" | updated_external: {yes_no(item['updated_external'])}"
        )

        if item.get("external_error"):
            print(f"   Aviso: {item['external_error']}")

        if index < total and args.delay > 0:
            time.sleep(args.delay)

    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 78)
    print("Resumo")
    print("=" * 78)
    print(f"Selecionados: {report['total_selected']}")
    print(f"Processados: {report['processed']}")
    print(f"HTTP 200: {report['success_http']}")
    print(f"Com preços reais: {report['with_real_prices']}")
    print(f"Com imagem real: {report['with_real_image']}")
    print(f"Atualização externa bem-sucedida: {report['updated_external']}")
    print(f"Fallback/sem oferta real: {report['fallback']}")
    print(f"Falhas HTTP/script: {report['failed']}")
    print(f"Relatório: {REPORT_FILE}")
    print("=" * 78)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProcesso interrompido pelo usuário.")
        sys.exit(1)
    except Exception as error:
        print(f"\nErro fatal: {error}")
        sys.exit(1)
