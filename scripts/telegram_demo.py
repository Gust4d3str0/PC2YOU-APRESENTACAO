"""Simulação offline por padrão; --enqueue insere uma promoção fictícia no MongoDB."""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.telegram_bot.alerts import parse_max_price
from services.telegram_bot.notifier import notification_text
from services.telegram_collector.config import load_settings
from services.telegram_collector.matcher import matches_alert, normalize_terms
from services.telegram_collector.parser import parse_message
from services.telegram_collector.repository import open_repository


def demo_promotion(query="RTX 5070", price="3599,90"):
    amount = parse_max_price(price)
    if amount is None:
        raise ValueError("A promoção fictícia precisa de um preço.")
    text = f"GALAX {query}\nPor R$ {str(amount).replace('.', ',')} no PIX\nKaBuM\nCupom GPU10\nhttps://www.kabum.com.br/"
    now = datetime.now(timezone.utc)
    return {"telegram": {"chat_id": -1009999999999, "chat_name": "SIMULAÇÃO LOCAL PC2YOU", "chat_username": None, "message_id": uuid4().int % (2**31 - 1) + 1, "message_url": None, "sent_at": now}, "raw_text": text, **parse_message(text), "status": "parsed", "created_at": now, "processed_at": now, "is_demo": True}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enqueue", action="store_true", help="Inserir no MongoDB para o worker do bot enviar aos alertas correspondentes")
    parser.add_argument("--query", default="RTX 5070")
    parser.add_argument("--price", default="3599,90")
    args = parser.parse_args()
    try:
        promotion = demo_promotion(args.query, args.price)
        if not args.enqueue:
            alert = {"query": args.query, "normalized_terms": normalize_terms(args.query), "max_price": parse_max_price("3800"), "enabled": True}
            print("Simulação offline. Correspondência:", matches_alert(promotion, alert))
            print(notification_text(promotion, alert))
            return
        settings = load_settings()
        client, repository = open_repository(settings)
        try:
            repository.ensure_indexes()
            repository.save(promotion)
            print("Promoção fictícia salva. O worker do bot avaliará os alertas ativos; mensagens reais podem ser enviadas aos seus usuários.")
        finally:
            client.close()
    except Exception as exc:
        print(f"Simulação interrompida ({type(exc).__name__}). Confira os argumentos e a conexão MongoDB.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
