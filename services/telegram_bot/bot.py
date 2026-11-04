import asyncio
import contextlib
import logging

from pymongo import MongoClient
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from services.telegram_collector.config import ConfigurationError, load_settings
from services.telegram_collector.logging_setup import configure_logging
from services.telegram_collector.repository import PromotionRepository
from .alerts import AlertRepository
from .handlers import AlertHandlers
from .notifier import NotificationWorker

logger = logging.getLogger("pc2you.telegram")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_message:
        await update.effective_message.reply_text(
            "Olá! Sou o PC2YOU, seu bot para acompanhar promoções de hardware. "
            "Use /acompanhar RTX 5070 para criar um alerta, /meuid para descobrir "
            "seu ID numérico e /ajuda para consultar os comandos."
        )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message:
        return
    settings = context.bot_data["settings"]
    try:
        summary = await asyncio.to_thread(context.bot_data["repository"].summary)
        collector = "online" if summary["collector_online"] else "offline ou sem sinal recente"
        text = (
            "PC2YOU: bot funcionando | MongoDB disponível\n"
            f"Promoções armazenadas: {summary['promotions']}\n"
            f"Fontes configuradas: {len(settings.allowed_chats)}\n"
            f"Coletor: {collector}\n"
            f"Fontes no último sinal do coletor: {summary['collector_sources']}"
        )
    except Exception as exc:
        logger.error("MongoDB indisponível ao consultar /status (%s)", type(exc).__name__)
        text = (
            "PC2YOU: bot funcionando | MongoDB indisponível\n"
            "Promoções armazenadas: indisponível\n"
            f"Fontes configuradas: {len(settings.allowed_chats)}\n"
            "Coletor: status indisponível"
        )
    await update.effective_message.reply_text(text)


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Falha no bot (%s)", type(context.error).__name__)


def build_application(settings, repository):
    if not settings.bot_token:
        raise ConfigurationError("Configure TELEGRAM_BOT_TOKEN para iniciar o bot.")
    app = (Application.builder().token(settings.bot_token).concurrent_updates(False)
           .post_init(start_worker).post_stop(stop_worker).post_shutdown(stop_worker).build())
    app.bot_data.update(settings=settings, repository=repository)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    if repository is not None:
        alerts = AlertRepository(repository.database)
        app.bot_data["alerts_repository"] = alerts
        AlertHandlers(alerts, settings).register(app)
    app.add_error_handler(handle_error)
    return app


async def start_worker(application):
    repository = application.bot_data.get("alerts_repository")
    if repository is not None:
        worker = NotificationWorker(repository, application.bot, application.bot_data["settings"])
        # Tarefa própria: é cancelada antes de encerrar o cliente Bot API.
        application.bot_data["notification_task"] = asyncio.create_task(worker.run_forever())


async def stop_worker(application):
    task = application.bot_data.pop("notification_task", None)
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def main():
    client = None
    try:
        settings = load_settings()
        configure_logging(settings)
        if not settings.bot_token:
            raise ConfigurationError("Configure TELEGRAM_BOT_TOKEN para iniciar o bot.")
        # MongoClient é lazy; /start permanece disponível mesmo com banco offline.
        client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=3000, connectTimeoutMS=3000, socketTimeoutMS=5000, tz_aware=True)
        repository = PromotionRepository(client[settings.mongo_db])
        app = build_application(settings, repository)
        logger.info("Iniciando bot PC2YOU")
        app.run_polling(allowed_updates=["message", "callback_query"], drop_pending_updates=False)
    except ConfigurationError as exc:
        print(f"[Telegram] {exc}")
        raise SystemExit(1) from None
    except Exception as exc:
        logger.error("Bot interrompido (%s). Confira token e conexão.", type(exc).__name__)
        raise SystemExit(1) from None
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    main()
