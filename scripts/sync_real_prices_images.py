import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path


API_URL = "http://localhost:8002"
DELAY_SECONDS = 1.2
REPORT_DIR = Path(__file__).resolve().parents[1] / "reports"
REPORT_FILE = REPORT_DIR / "sync_real_prices_images_report.json"
CANDIDATES_REPORT_FILE = REPORT_DIR / "sync_real_prices_images_candidates.json"


def request_json(url, method="GET", timeout=60):
    req = urllib.request.Request(url, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8")
        try:
            return error.code, json.loads(body)
        except Exception:
            return error.code, {"error": body}
    except Exception as error:
        return 0, {"error": str(error)}


def api_url(base_url, path):
    return f"{base_url.rstrip('/')}{path}"


def get_components(base_url):
    status, data = request_json(api_url(base_url, "/components"))

    if status != 200:
        raise RuntimeError(f"Erro ao buscar componentes: {status} - {data}")

    if not isinstance(data, list):
        raise RuntimeError(f"Resposta inesperada em /components: {data}")

    return data


def refresh_component(base_url, component_id):
    status, data = request_json(
        api_url(base_url, f"/components/{component_id}/refresh-real-prices"),
        method="POST",
        timeout=90,
    )

    return status, data


def get_component(base_url, component_id):
    return request_json(api_url(base_url, f"/components/{component_id}"))


def has_real_price(component):
    for price in component.get("prices", []) or []:
        if price.get("source") == "mercado_livre" or price.get("store") == "Mercado Livre":
            return True
    return False


def has_real_image(component):
    return bool(component.get("real_image"))


def category_matches(component, category):
    if not category:
        return True
    component_category = component.get("category")
    if category == "ram":
        return component_category in {"ram", "kit-ram"}
    return component_category == category


def filter_components(components, args):
    selected = [component for component in components if category_matches(component, args.category)]
    if args.only_missing:
        selected = [
            component
            for component in selected
            if not has_real_price(component) and not has_real_image(component)
        ]
    return selected


def write_replace_candidates(components, args):
    candidates = [
        {
            "id": component.get("id"),
            "name": component.get("name"),
            "category": component.get("category"),
            "brand": component.get("brand"),
            "has_real_price": has_real_price(component),
            "has_real_image": has_real_image(component),
        }
        for component in filter_components(components, args)
        if not has_real_price(component) and not has_real_image(component)
    ]

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "api_url": args.api_url,
        "category": args.category,
        "total_candidates": len(candidates),
        "candidates": candidates,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with open(CANDIDATES_REPORT_FILE, "w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    print(f"Candidatos sem ML: {len(candidates)}")
    for item in candidates:
        print(f" - {item['id']} | {item['category']} | {item['name']}")
    print(f"Relatório salvo em: {CANDIDATES_REPORT_FILE}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Atualiza preços e imagens reais dos componentes via Mercado Livre."
    )
    parser.add_argument("--api-url", default=API_URL, help="URL base da API de catálogo.")
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="Atualiza só componentes sem preço real e sem imagem real.",
    )
    parser.add_argument(
        "--category",
        help="Filtra por categoria. Use ram para incluir ram e kit-ram.",
    )
    parser.add_argument(
        "--replace-candidates",
        action="store_true",
        help="Lista componentes ainda sem ML para apoiar substituição no seed, sem atualizar.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 72)
    print("PC2YOU — Atualização de preços reais e imagens reais")
    print("=" * 72)

    components = get_components(args.api_url)
    if args.replace_candidates:
        write_replace_candidates(components, args)
        return

    selected_components = filter_components(components, args)
    total = len(selected_components)

    print(f"Componentes encontrados: {len(components)}")
    if args.category:
        print(f"Filtro de categoria: {args.category}")
    if args.only_missing:
        print("Modo: apenas componentes sem preço real e sem imagem real")
    print(f"Componentes selecionados: {total}")
    print()

    report = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "api_url": args.api_url,
        "category": args.category,
        "only_missing": args.only_missing,
        "source_total_components": len(components),
        "total_components": total,
        "updated": 0,
        "with_real_prices": 0,
        "with_real_image": 0,
        "without_real_offers": 0,
        "failed": 0,
        "items": [],
    }

    for index, component in enumerate(selected_components, start=1):
        component_id = component.get("id")
        name = component.get("name", component_id)

        if not component_id:
            continue

        print(f"[{index:03d}/{total}] Atualizando: {name} ({component_id})")

        status, data = refresh_component(args.api_url, component_id)
        data = data if isinstance(data, dict) else {"response": data}

        item_report = {
            "id": component_id,
            "name": name,
            "category": component.get("category"),
            "status_code": status,
            "updated_external": bool(data.get("updated_external")),
            "offers_found": data.get("offers_found", 0),
            "offers_used": data.get("offers_used", 0),
            "external_error": data.get("external_error"),
            "real_prices_count": 0,
            "real_image": None,
            "image_source": None,
        }

        summary = data.get("summary") or {}
        item_report["real_prices_count"] = summary.get("real_prices_count", 0)

        # Depois do refresh, busca o componente completo para verificar imagem real.
        component_status, component_data = get_component(args.api_url, component_id)

        if component_status == 200 and isinstance(component_data, dict):
            item_report["real_image"] = component_data.get("real_image")
            item_report["image_source"] = component_data.get("image_source")

        if status == 200:
            report["updated"] += 1

            if item_report["real_prices_count"] > 0:
                report["with_real_prices"] += 1

            if item_report["real_image"]:
                report["with_real_image"] += 1

            if not data.get("updated_external"):
                report["without_real_offers"] += 1

            print(
                f"   OK | preços reais: {item_report['real_prices_count']} | "
                f"imagem real: {'sim' if item_report['real_image'] else 'não'}"
            )

            if data.get("external_error"):
                print(f"   Aviso: {data.get('external_error')}")
        else:
            report["failed"] += 1
            print(f"   ERRO {status}: {data}")

        report["items"].append(item_report)

        if index < total:
            time.sleep(DELAY_SECONDS)

    report["finished_at"] = datetime.now().isoformat(timespec="seconds")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    print()
    print("=" * 72)
    print("Resumo")
    print("=" * 72)
    print(f"Total: {report['total_components']}")
    print(f"Atualizados: {report['updated']}")
    print(f"Com preços reais: {report['with_real_prices']}")
    print(f"Com imagem real: {report['with_real_image']}")
    print(f"Sem oferta real liberada: {report['without_real_offers']}")
    print(f"Falhas: {report['failed']}")
    print(f"Relatório salvo em: {REPORT_FILE}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProcesso interrompido pelo usuário.")
        sys.exit(1)
    except Exception as error:
        print(f"\nErro fatal: {error}")
        sys.exit(1)
