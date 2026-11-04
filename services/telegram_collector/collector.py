import argparse
import asyncio
import contextlib
import logging
import os
from datetime import datetime, timezone

from telethon import TelegramClient, events, utils
from telethon.tl.types import Channel, Chat

from .config import ConfigurationError, load_settings
from .deduplication import message_identity
from .filters import is_possible_promotion
from .logging_setup import configure_logging
from .models import PromotionStatus
from .parser import parse_message
from .links import extract_message_links
from .repository import open_repository


logger = logging.getLogger("pc2you.telegram")


def is_allowed_source(chat_id, entity, allowed_chats) -> bool:
    return chat_id in allowed_chats and isinstance(entity, (Chat, Channel)) and not getattr(entity, "left", False)


def message_url(entity, message_id: int) -> str | None:
    username = getattr(entity, "username", None)
    if username:
        return f"https://t.me/{username}/{message_id}"
    if isinstance(entity, Channel):
        return f"https://t.me/c/{entity.id}/{message_id}"
    return None


async def process_message(message, entity, settings, repository) -> bool:
    chat_id = utils.get_peer_id(entity)
    # Defesa em profundidade: histórico e eventos passam pela mesma verificação.
    if not is_allowed_source(chat_id, entity, settings.allowed_chats):
        return False
    text = getattr(message, "message", None)
    if getattr(message, "out", False) or getattr(message, "action", None) or not is_possible_promotion(text):
        logger.info("Mensagem ignorada: chat_id=%s message_id=%s", chat_id, message.id)
        return False
    logger.info("Possível promoção detectada: chat_id=%s message_id=%s", chat_id, message.id)
    now = datetime.now(timezone.utc)
    sent_at = getattr(message, "date", None)
    if sent_at is not None and sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=timezone.utc)
    parsed = parse_message(text, sent_at=sent_at, **extract_message_links(message))
    document = {
        "telegram": {
            "chat_id": chat_id,
            "chat_name": getattr(entity, "title", None),
            "chat_username": getattr(entity, "username", None),
            "message_id": message.id,
            "message_url": message_url(entity, message.id),
            "sent_at": sent_at,
        },
        "raw_text": text,
        **parsed,
        "status": PromotionStatus.PARSED.value,
        "created_at": now,
        "processed_at": now,
    }
    saved = await asyncio.to_thread(repository.save, document)
    logger.info("%s: chat_id=%s message_id=%s", "Promoção salva" if saved else "Mensagem já salva; links complementados quando disponíveis", chat_id, message.id)
    if saved and LINK_RESOLUTION_ENABLED:
        _resolve_in_background(repository, message_identity(chat_id, message.id))
    return saved


_background = set()
LINK_RESOLUTION_ENABLED = True


def _resolve_in_background(repository, identity):
    """Link resolution is best effort and must not delay or break message processing."""
    async def run():
        try:
            await asyncio.to_thread(repository.resolve_link, identity)
        except Exception as exc:
            logger.warning("Resolução de link falhou (%s); offer.url original mantida", type(exc).__name__)
    task = asyncio.ensure_future(run())
    _background.add(task)
    task.add_done_callback(_background.discard)


async def list_chats(client):
    print("ID\tTIPO\tNOME")
    async for dialog in client.iter_dialogs():
        if isinstance(dialog.entity, (Chat, Channel)):
            kind = "canal" if getattr(dialog.entity, "broadcast", False) else "grupo"
            name = (dialog.name or "(sem nome)").replace("\n", " ").replace("\t", " ")
            print(f"{dialog.id}\t{kind}\t{name}")


async def resolve_sources(client, settings):
    sources = {}
    # Preenche o cache de access_hash do Telethon sem ler conteúdo dos chats.
    async for dialog in client.iter_dialogs():
        if is_allowed_source(dialog.id, dialog.entity, settings.allowed_chats):
            sources[dialog.id] = dialog.entity
    missing = settings.allowed_chats - sources.keys()
    if missing:
        raise ConfigurationError("Algumas fontes não estão acessíveis. Confira os IDs com list-chats e a participação da conta.")
    return sources


async def import_history(client, sources, settings, repository, limit: int):
    saved = 0
    for chat_id, entity in sources.items():
        logger.info("Importando até %s mensagens: chat_id=%s", limit, chat_id)
        async for message in client.iter_messages(entity, limit=limit):
            # Falha de persistência interrompe a importação para permitir repetição segura.
            saved += await process_message(message, entity, settings, repository)
    logger.info("Importação concluída: %s promoções novas salvas", saved)
    return saved


async def keep_heartbeat(client, repository, source_count):
    while True:
        try:
            await asyncio.to_thread(repository.heartbeat, source_count, connected=client.is_connected())
        except Exception as exc:
            logger.error("Falha ao atualizar status do coletor (%s)", type(exc).__name__)
        await asyncio.sleep(30)


async def run(args, settings):
    settings.require_account(authentication=args.command == "auth")
    if args.command in {"listen", "import-history"}:
        settings.require_sources()
    settings.session_path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(settings.session_path.parent, 0o700)
    client = TelegramClient(str(settings.session_path), settings.api_id, settings.api_hash)
    mongo_client = None
    heartbeat_task = None
    repository = None
    listening = False
    try:
        if args.command == "auth":
            await client.start(phone=settings.phone)
        else:
            await client.connect()
            if not await client.is_user_authorized():
                raise ConfigurationError("Sessão ausente ou expirada. Execute o comando auth em um terminal interativo.")
        me = await client.get_me()
        if me is None or me.bot:
            raise ConfigurationError("O coletor precisa da sessão de uma conta de usuário, não de um bot.")
        logger.info("Conectado")
        if args.command == "auth":
            logger.info("Conta autenticada; sessão persistida")
            return
        if args.command == "list-chats":
            await list_chats(client)
            return
        sources = await resolve_sources(client, settings)
        logger.info("%s fontes configuradas", len(sources))
        mongo_client, repository = await asyncio.to_thread(open_repository, settings)
        await asyncio.to_thread(repository.ensure_indexes)
        if args.command == "import-history":
            await import_history(client, sources, settings, repository, args.limit or settings.history_limit)
            return

        async def on_message(event):
            if event.is_private or event.chat_id not in sources:
                return
            try:
                logger.info("Nova mensagem recebida: chat_id=%s message_id=%s", event.chat_id, event.id)
                await process_message(event.message, sources[event.chat_id], settings, repository)
            except Exception as exc:
                logger.error("Falha ao processar mensagem; repita import-history para recuperá-la (%s)", type(exc).__name__)

        client.add_event_handler(on_message, events.NewMessage(chats=list(sources), incoming=True))
        listening = True
        await asyncio.to_thread(repository.heartbeat, len(sources))
        heartbeat_task = asyncio.create_task(keep_heartbeat(client, repository, len(sources)))
        # Handler registrado antes do backfill; o índice trata a sobreposição.
        if args.import_history:
            await import_history(client, sources, settings, repository, args.limit or settings.history_limit)
        logger.info("Ouvindo novas mensagens")
        await client.run_until_disconnected()
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task
        if listening and repository:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(repository.heartbeat, len(settings.allowed_chats), connected=False)
        await client.disconnect()
        if mongo_client is not None:
            mongo_client.close()
        session_file = settings.session_path
        if session_file.suffix != ".session":
            session_file = session_file.with_name(session_file.name + ".session")
        if session_file.exists():
            os.chmod(session_file, 0o600)


def positive_int(value):
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Use um inteiro positivo.") from None
    if number <= 0:
        raise argparse.ArgumentTypeError("Use um inteiro positivo.")
    return number


def main():
    parser = argparse.ArgumentParser(description="Coletor Telegram do PC2YOU")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("auth", help="Autenticar conta interativamente")
    commands.add_parser("list-chats", help="Listar somente grupos e canais")
    history = commands.add_parser("import-history", help="Importar mensagens anteriores e encerrar")
    history.add_argument("--limit", type=positive_int)
    listen = commands.add_parser("listen", help="Ouvir novas mensagens")
    listen.add_argument("--import-history", action="store_true")
    listen.add_argument("--limit", type=positive_int)
    args = parser.parse_args()
    try:
        settings = load_settings()
        configure_logging(settings)
        asyncio.run(run(args, settings))
    except ConfigurationError as exc:
        # Mensagens da configuração são controladas e nunca incluem os valores.
        print(f"[Telegram] {exc}")
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        logger.info("Coletor encerrado")
    except Exception as exc:
        logger.error("Operação interrompida (%s). Confira conexão, configuração e sessão.", type(exc).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
