import logging
from os import getenv
from typing import Any, Awaitable, Callable, Dict, Optional
import time
from aiogram import BaseMiddleware
from aiogram.types import ReplyKeyboardRemove, TelegramObject
from cachetools import TTLCache

from core.services.currency_converter import AsyncCurrencyConverter
from core.services.db import DatabaseService
from core.helper_classes import Context, ServiceHub
from core.services.media_saver import MediaSaver
from core.services.notifications import NotificatorHub
from core.services.placeholders import PlaceholderManager
from core.services.tax import TaxSystem
from core.states import NewUserStates
from ui.translates import TranslatorHub


class ContextMiddleware(BaseMiddleware):
    def __init__(self):
        super().__init__()
        self.initialized = False
        self.services: Optional[ServiceHub] = None
    
    async def start(self, bot):
        if self.initialized: return
        db = DatabaseService()
            
        self.services = ServiceHub(
            db=db,
            tax=TaxSystem(),
            notificators=NotificatorHub(bot=bot,
                                        logs_channel_id=int(env_var) if (env_var := getenv("TG_LOGS_CHANNEL_ID")) else None,
                                        admin_chat_id=int(env_var) if (env_var := getenv("TG_ADMIN_CHAT_ID")) else None),
            placeholders=PlaceholderManager(db.placeholders),
            currency_converter=AsyncCurrencyConverter(),
            media_saver=MediaSaver(bot=bot)
        )
        
        await self.services.db.prepare()
        
        self.initialized = True

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user_id = data["event_from_user"].id

        customer = await self.services.db.customers.find_by_user_id(user_id)
        if customer and customer.banned:
            try:
                return await (event.message or event.callback_query.message).answer("You are banned.", reply_keyboard=ReplyKeyboardRemove())
            except:
                return
            
        lang = customer.lang if customer and customer.lang else "?"                          

        data["ctx"] = Context(event.message or event.callback_query,
                              data.get("state"),
                              customer,
                              lang,
                              TranslatorHub.get_for_lang(lang, self.services.placeholders),
                              self.services)
        state = await data.get("state").get_state()
        if not customer and not state == NewUserStates.LangChoosing and state != None:
            await data["ctx"].fsm.set_state(NewUserStates.LangChoosing)
            return await data["ctx"].message.answer("Account deleted. Enter /start.", reply_keyboard=ReplyKeyboardRemove())

        try:
            if hasattr(event, "message") and event.message: await data["ctx"].update_messages_log(event.message)
        except Exception as e: 
            logging.getLogger(__name__).exception(f"Failed to update messages log: {e}")
        
        return await handler(event, data)
    
    async def stop(self):
        if not self.initialized: return
        
        if self.services.notificators: await self.services.notificators.stop()
        if self.services.db: await self.services.db.close()
        if self.services.tax: await self.services.tax.close()
        if self.services.placeholders: await self.services.placeholders.close()
        if self.services.currency_converter: await self.services.currency_converter.close()
        if self.services.media_saver: await self.services.media_saver.close()
        
class ErrorLoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as e:
            await data["ctx"].services.notificators.TelegramChannelLogs.send_error(data["ctx"], e)
            raise e

class ThrottlingMiddleware(BaseMiddleware):
    default = TTLCache(maxsize=25_000, ttl=.25)
    # Храним временные метки запросов пользователя (user_id -> [timestamps])
    user_requests = TTLCache(maxsize=25_000, ttl=30)
    # Храним "забаненных" пользователей (user_id -> время окончания бана)
    banned_users = TTLCache(maxsize=25_000, ttl=15)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        chat = None
        if event.message:
            chat = event.message.chat
        elif event.callback_query:
            chat = event.callback_query.message.chat
        
        if chat and chat.type != "private":
            return
        
        user_id = data["event_from_user"].id
        # Проверяем, не забанен ли пользователь
        if user_id in self.banned_users:
            return
        
        if user_id in self.default:
            now = time.time()
            # Получаем список временных меток запросов пользователя
            timestamps = self.user_requests.get(user_id, [])
            # Оставляем только те, что были за последние 30 секунд
            timestamps = [ts for ts in timestamps if now - ts < 30]
            timestamps.append(now)
            self.user_requests[user_id] = timestamps

            if len(timestamps) > 5:
                # Баним пользователя на 15 секунд
                self.banned_users[user_id] = None
                return await getattr(event, "message", event).answer("Throttled for 15 seconds.")
        else:
            self.default[user_id] = None

        return await handler(event, data)

class RoleCheckMiddleware(BaseMiddleware):
    def __init__(self, allowed: list[str] | str):
        self.allowed = allowed

    async def __call__(self, handler, event, data):
        ctx: Context = data["ctx"]

        if (not ctx or
                not ctx.customer or
                ((ctx.customer.role != self.allowed) if isinstance(self.allowed, str) else (ctx.customer.role in self.allowed))):

            return

        return await handler(event, data)