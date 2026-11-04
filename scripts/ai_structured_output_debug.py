"""Diagnose the actual AI v1 contract without printing response prose or secrets."""

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "api-orcamentos"))
    sys.path.insert(0, str(root / "services"))
    from dotenv import load_dotenv
    load_dotenv(root / ".env", override=False)
    from ai import AIService
    from ai.errors import AIError, AIInvalidResponseError
    from ai.schemas import AnalyzePCRequest
    from ai_context import build_context
    from ai_analyze_pc_demo import PAYLOAD, mock_app

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true", help="Same service/contract with simulated provider and catalog; no network")
    parser.add_argument("--catalog-url", default="http://localhost:8002", help="Internal catalog URL (default: http://localhost:8002)")
    parser.add_argument("--without-catalog", action="store_true", help="Isolate provider using only user-reported components and partial compatibility")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    class UnknownCatalog:
        def search_components(self, *args):
            return []

        def list_components(self, *args):
            return []

    try:
        if args.mock:
            mock_app()
            import ai_routes
            from main import app
            service = ai_routes.get_ai_service()
            catalog = app.dependency_overrides[ai_routes.get_ai_catalog]()
        else:
            service = AIService()
            catalog = UnknownCatalog()
            if not args.without_catalog:
                from catalog_client import CatalogClient
                from settings import get_settings
                catalog = CatalogClient(replace(get_settings(), catalog_api_url=args.catalog_url.rstrip("/")))
        print(f"Provider: {service.provider.name}")
        print(f"Model: {service.settings.model}")
        service.ensure_available()
        context = build_context(AnalyzePCRequest.model_validate(PAYLOAD), catalog)
        service.analyze_pc(context)
        print("Structured output: OK\nSchema validation: OK\nSemantic validation: OK")
        return 0
    except AIInvalidResponseError as exc:
        print("Response validation: FAILED")
        for issue in exc.issues:
            print(f"Field: {issue['field']}\nExpected: {issue['expected']}\nReceived: {issue['received']}\nCategory: {issue['category']}")
    except AIError as exc:
        print(f"Provider/configuration: FAILED\nCode: {exc.code}")
    except Exception as exc:
        # Unexpected local/catalog errors remain distinct; never print raw exception text.
        print(f"Local/context: FAILED\nError type: {type(exc).__name__}")
        import traceback
        for frame in traceback.extract_tb(exc.__traceback__):
            print(f"Location: {Path(frame.filename).name}:{frame.lineno} ({frame.name})")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
