import asyncio
import logging
import time
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from bson import ObjectId
from pymongo.errors import PyMongoError
from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup as Keyboard
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters

from services.telegram_collector.matcher import COMPONENT_TYPES, detect_component_type, normalize_terms
from .alerts import format_money, parse_max_price, validate_alert
from .notifier import notification_text


logger = logging.getLogger("pc2you.telegram")
DRAFT_KEY = "price_alert_draft"
FIELDS = {"query": "Produto/modelo", "max_price": "Preço máximo", "component_type": "Tipo", "brands": "Marcas permitidas", "ignored_brands": "Marcas ignoradas", "stores": "Lojas permitidas", "ignored_stores": "Lojas ignoradas", "minimum_discount": "Desconto mínimo (%)"}


def user_allowed(settings, user_id):
    return isinstance(user_id, int) and user_id > 0 and (not settings.allowed_users or user_id in settings.allowed_users)


class AlertHandlers:
    def __init__(self, repository, settings):
        self.repo = repository
        self.settings = settings

    async def guard(self, update):
        user_id = getattr(update.effective_user, "id", None)
        private = getattr(update.effective_chat, "type", None) == "private"
        if user_allowed(self.settings, user_id) and private:
            return True
        text = "Este bot é privado. Seu ID não está autorizado." if not user_allowed(self.settings, user_id) else "Use este comando em uma conversa privada comigo."
        if update.callback_query:
            await update.callback_query.answer(text, show_alert=True)
        elif update.effective_message:
            await update.effective_message.reply_text(text)
        return False

    def safe(self, handler, *, personal=True):
        async def wrapped(update, context):
            if personal and not await self.guard(update):
                return
            try:
                await handler(update, context)
            except PyMongoError as exc:
                logger.error("[Bot] MongoDB indisponível (%s)", type(exc).__name__)
                await update.effective_message.reply_text("O banco está indisponível. Tente novamente em instantes; seus alertas salvos foram preservados.")
        return wrapped

    async def help(self, update, context):
        await update.effective_message.reply_text(
            "PC2YOU — comandos\n/start — apresentação\n/status — saúde do sistema\n"
            "/meuid — seu ID numérico do Telegram\n/acompanhar [modelo] — criar alerta\n"
            "/alertas — listar, editar, pausar ou ativar\n/remover [número] — remover com confirmação\n"
            "/pausar [número] — pausar sem apagar\n/ofertas — até 10 ofertas recentes relevantes\n"
            "/cancelar — cancelar um cadastro\n/ajuda — esta lista"
        )

    async def my_id(self, update, context):
        if getattr(update.effective_chat, "type", None) != "private":
            await update.effective_message.reply_text("Envie /meuid em uma conversa privada comigo.")
            return
        await update.effective_message.reply_text(f"Seu telegram_user_id: {update.effective_user.id}")

    def draft(self, context, token=None):
        draft = context.user_data.get(DRAFT_KEY)
        if draft and draft["expires_at"] >= time.time() and (token is None or draft["token"] == token):
            return draft
        if draft and draft["expires_at"] < time.time():
            context.user_data.pop(DRAFT_KEY, None)
        return None

    async def follow(self, update, context):
        query = " ".join(context.args or []).strip()
        context.user_data[DRAFT_KEY] = {"token": uuid4().hex[:8], "creation_id": str(ObjectId()), "expires_at": time.time() + 900, "field": "max_price" if query else "query", "values": {"query": query, "component_type": detect_component_type(query), "max_price": None, "brands": [], "ignored_brands": [], "stores": [], "ignored_stores": [], "minimum_discount": None, "enabled": True}}
        if query and (not normalize_terms(query) or len(query) > 120):
            context.user_data[DRAFT_KEY]["field"] = "query"
            await update.effective_message.reply_text("Informe um modelo válido com até 120 caracteres.")
            return
        await update.effective_message.reply_text("Até quanto você pretende pagar? Ex.: 3800 ou R$ 3.800,00. Use 'sem limite' se preferir." if query else "Qual peça você quer acompanhar?")

    async def show_summary(self, message, draft):
        draft["field"] = None
        values = draft["values"]
        text = f"🔔 {'EDITAR' if draft.get('alert_id') else 'NOVO'} ALERTA\n\nProduto: {values['query']}\nPreço máximo: {format_money(values.get('max_price'))}\nTipo: {values.get('component_type') or 'por texto'}\nEstado: {'ativo' if values['enabled'] else 'pausado'}"
        for field in ("brands", "ignored_brands", "stores", "ignored_stores", "minimum_discount"):
            value = values.get(field)
            if value is not None and value != []:
                text += "\n" + FIELDS[field] + ": " + (", ".join(value) if isinstance(value, list) else str(value))
        text += "\n\nDeseja salvar esse alerta?" if draft.get("alert_id") or not values["enabled"] else "\n\nDeseja ativar esse alerta?"
        token = draft["token"]
        await message.reply_text(text, reply_markup=Keyboard([
            [Button("✅ Salvar" if draft.get("alert_id") or not values["enabled"] else "✅ Ativar", callback_data=f"pc2:save:{token}"), Button("❌ Cancelar", callback_data=f"pc2:cancel:{token}")],
            [Button("⚙️ Mais filtros", callback_data=f"pc2:filters:{token}")],
        ]))

    async def show_filters(self, message, draft):
        token = draft["token"]
        rows = [[Button(label, callback_data=f"pc2:field:{token}:{field}")] for field, label in FIELDS.items()]
        rows.extend([[Button("⏯ Alternar ativo/pausado", callback_data=f"pc2:toggle:{token}")], [Button("↩️ Resumo", callback_data=f"pc2:summary:{token}")]])
        await message.reply_text("Selecione o filtro que deseja editar. Use '-' para limpar listas, desconto ou tipo.", reply_markup=Keyboard(rows))

    async def text(self, update, context):
        draft = self.draft(context)
        if draft is None:
            return
        field = draft.get("field")
        if field is None:
            await update.effective_message.reply_text("Use os botões do resumo ou /cancelar.")
            return
        value = update.effective_message.text.strip()
        candidate = deepcopy(draft["values"])
        try:
            if field == "query":
                if not normalize_terms(value) or len(value) > 120 or "\n" in value:
                    raise ValueError("Informe o modelo em uma linha, com até 120 caracteres.")
                candidate["query"] = value
                candidate["component_type"] = detect_component_type(value)
            elif field == "max_price":
                candidate[field] = parse_max_price(value)
            elif field == "component_type":
                candidate[field] = None if value == "-" else value.lower()
                if candidate[field] is not None and candidate[field] not in COMPONENT_TYPES:
                    raise ValueError("Use gpu, cpu, motherboard, ram, storage, psu, case, cooler ou '-'.")
            elif field == "minimum_discount":
                candidate[field] = None if value == "-" else Decimal(value.rstrip("%").strip().replace(",", "."))
            else:
                if field.startswith("ignored_") and value.lower().startswith("ignorar:"):
                    value = value.split(":", 1)[1].strip()
                candidate[field] = [] if value == "-" else [item.strip() for item in value.split(",") if item.strip()]
            candidate = validate_alert(candidate)
        except (ValueError, InvalidOperation):
            await update.effective_message.reply_text("Valor inválido. Use um preço positivo em reais, filtros separados por vírgula ou desconto entre 0 e 100. /cancelar encerra o cadastro.")
            return
        draft["values"] = candidate
        if field == "query" and not draft.get("editing_field"):
            draft["field"] = "max_price"
            await update.effective_message.reply_text("Até quanto você pretende pagar? Ex.: 3800 ou R$ 3.800,00.")
        else:
            draft.pop("editing_field", None)
            await self.show_summary(update.effective_message, draft)

    async def cancel(self, update, context):
        context.user_data.pop(DRAFT_KEY, None)
        await update.effective_message.reply_text("Cadastro cancelado. Seus alertas salvos foram mantidos.")

    async def list_alerts(self, update, context, offset=0):
        user_id = update.effective_user.id
        alerts = await asyncio.to_thread(self.repo.list_owned, user_id, offset, 11)
        if not alerts:
            await update.effective_message.reply_text("Você ainda não tem alertas nesta página. Use /acompanhar RTX 5070.")
            return
        text = ["🔔 SEUS ALERTAS"]
        rows = []
        for index, alert in enumerate(alerts[:10], offset + 1):
            text.append(f"{index}. {alert['query']}\nAté {format_money(alert.get('max_price'))}\n{'✅ Ativo' if alert['enabled'] else '⏸ Pausado'}")
            identity = alert["_id"]
            action = "pause" if alert["enabled"] else "resume"
            rows.append([Button(f"✏️ Editar {index}", callback_data=f"pc2:edit:{identity}"), Button("⏸ Pausar" if alert["enabled"] else "▶️ Ativar", callback_data=f"pc2:{action}:{identity}"), Button("🗑 Remover", callback_data=f"pc2:remove:{identity}")])
        navigation = []
        if offset:
            navigation.append(Button("⬅️ Anterior", callback_data=f"pc2:list:{max(0, offset - 10)}"))
        if len(alerts) > 10:
            navigation.append(Button("Próxima ➡️", callback_data=f"pc2:list:{offset + 10}"))
        if navigation:
            rows.append(navigation)
        await update.effective_message.reply_text("\n\n".join(text), reply_markup=Keyboard(rows))

    async def confirm_remove(self, message, alert):
        await message.reply_text(f"Deseja realmente remover o alerta:\n\n{alert['query']} — até {format_money(alert.get('max_price'))}?", reply_markup=Keyboard([[Button("✅ Remover", callback_data=f"pc2:delete:{alert['_id']}"), Button("❌ Cancelar", callback_data="pc2:noop")]]))

    async def indexed_action(self, update, context, action):
        if not context.args:
            await self.list_alerts(update, context)
            return
        if len(context.args) != 1 or not context.args[0].isdigit() or not 1 <= int(context.args[0]) <= 10000:
            await update.effective_message.reply_text("Use o número exibido em /alertas ou escolha os botões.")
            return
        owned = await asyncio.to_thread(self.repo.list_owned, update.effective_user.id, int(context.args[0]) - 1, 1)
        if not owned:
            await update.effective_message.reply_text("Alerta não encontrado. Confira /alertas.")
            return
        if action == "remove":
            await self.confirm_remove(update.effective_message, owned[0])
        else:
            await asyncio.to_thread(self.repo.set_enabled, update.effective_user.id, owned[0]["_id"], False)
            await update.effective_message.reply_text("⏸ Alerta pausado. Você pode reativá-lo em /alertas.")

    async def remove(self, update, context):
        await self.indexed_action(update, context, "remove")

    async def pause(self, update, context):
        await self.indexed_action(update, context, "pause")

    async def offers(self, update, context):
        offers = await asyncio.to_thread(self.repo.recent_for_user, update.effective_user.id)
        if not offers:
            await update.effective_message.reply_text("Nenhuma oferta recente corresponde aos seus alertas ativos.")
            return
        await update.effective_message.reply_text("🔥 OFERTAS PARA VOCÊ")
        for promotion in offers:
            offer = promotion.get("offer") or {}
            text = notification_text(promotion, {"query": "Oferta", "max_price": None}).replace("🚨 PC2YOU — OFERTA ENCONTRADA", "🔥 PC2YOU — OFERTA RECENTE")
            from services.telegram_collector.parser import extract_urls

            links = extract_urls("", [offer.get("url")])
            markup = Keyboard([[Button("🛒 Abrir oferta", url=links[0])]]) if links else None
            await update.effective_message.reply_text(text, reply_markup=markup)

    async def callback(self, update, context):
        callback = update.callback_query
        await callback.answer()
        parts = (callback.data or "").split(":")
        if len(parts) < 2:
            return
        action = parts[1]
        identity = parts[2] if len(parts) > 2 else ""
        message = update.effective_message
        user_id = update.effective_user.id
        if action == "noop":
            await message.reply_text("Operação cancelada.")
            return
        if action == "list":
            if identity.isdigit() and 0 <= int(identity) <= 10000:
                await self.list_alerts(update, context, int(identity))
            return
        if action in {"save", "cancel", "summary", "filters", "field", "toggle"}:
            draft = self.draft(context, identity)
            if draft is None:
                await message.reply_text("Este cadastro expirou ou foi substituído. Use /acompanhar ou /alertas.")
                return
            if action == "cancel":
                await self.cancel(update, context)
            elif action == "save":
                if draft.get("alert_id"):
                    saved = await asyncio.to_thread(self.repo.update, user_id, draft["alert_id"], draft["values"])
                    if not saved:
                        await message.reply_text("Alerta não encontrado. Confira /alertas.")
                        return
                else:
                    await asyncio.to_thread(self.repo.create, user_id, draft["values"], creation_id=draft["creation_id"])
                context.user_data.pop(DRAFT_KEY, None)
                logger.info("[Alert] Alerta %s", "atualizado" if draft.get("alert_id") else "criado")
                await message.reply_text(f"✅ Alerta {'atualizado' if draft.get('alert_id') else 'criado'}\n{draft['values']['query']}\nAté {format_money(draft['values'].get('max_price'))}\n{'Ativo' if draft['values']['enabled'] else 'Pausado'}")
            elif action == "filters":
                await self.show_filters(message, draft)
            elif action == "field" and len(parts) == 4 and parts[3] in FIELDS:
                draft.update(field=parts[3], editing_field=True)
                await message.reply_text(f"Informe {FIELDS[parts[3]].lower()}. Listas: separe por vírgulas; '-' limpa o filtro. Preço: 3800,00 ou 'sem limite'.")
            else:
                if action == "toggle":
                    draft["values"]["enabled"] = not draft["values"]["enabled"]
                await self.show_summary(message, draft)
            return
        if action == "ignore":
            try:
                history_id = ObjectId(identity)
            except Exception:
                return
            result = await asyncio.to_thread(self.repo.history.update_one, {"_id": history_id, "telegram_user_id": user_id}, {"$set": {"dismissed": True}})
            await message.reply_text("Oferta ignorada." if result.matched_count else "Notificação não encontrada.")
            return
        alert = await asyncio.to_thread(self.repo.get_owned, user_id, identity)
        if alert is None:
            await message.reply_text("Alerta não encontrado. Confira /alertas.")
            return
        if action == "edit":
            values = {field: alert.get(field) for field in (*FIELDS, "enabled")}
            context.user_data[DRAFT_KEY] = {"token": uuid4().hex[:8], "expires_at": time.time() + 900, "field": None, "alert_id": str(alert["_id"]), "values": values}
            await self.show_summary(message, context.user_data[DRAFT_KEY])
        elif action == "remove":
            await self.confirm_remove(message, alert)
        elif action == "delete":
            await asyncio.to_thread(self.repo.remove, user_id, alert["_id"])
            await message.reply_text("🗑 Alerta removido.")
        elif action in {"pause", "resume"}:
            await asyncio.to_thread(self.repo.set_enabled, user_id, alert["_id"], action == "resume")
            logger.info("[Bot] Alerta %s", "reativado" if action == "resume" else "pausado")
            await message.reply_text("▶️ Alerta ativado." if action == "resume" else "⏸ Alerta pausado.")

    def register(self, application):
        # Grupo 0 preserva os comandos de saúde existentes. Grupo 1 contém
        # fluxos pessoais, callbacks e respostas de conversas.
        for name, callback in {"acompanhar": self.follow, "alertas": self.list_alerts, "remover": self.remove, "pausar": self.pause, "ofertas": self.offers, "cancelar": self.cancel}.items():
            application.add_handler(CommandHandler(name, self.safe(callback)), group=1)
        application.add_handler(CommandHandler("ajuda", self.safe(self.help, personal=False)), group=1)
        application.add_handler(CommandHandler("meuid", self.safe(self.my_id, personal=False)), group=1)
        application.add_handler(CallbackQueryHandler(self.safe(self.callback), pattern=r"^pc2:"), group=1)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.safe(self.text)), group=1)
