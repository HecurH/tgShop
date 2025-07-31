from typing import Any
import time
from aiogram import BaseMiddleware
from aiogram.types import ReplyKeyboardRemove
from cachetools import TTLCache

from core.db import DatabaseService
from core.helper_classes import Context
from core.states import NewUserStates


class ContextMiddleware(BaseMiddleware):
    def __init__(self):
        self.db = DatabaseService()
        self.initialized = False

    async def __call__(self, handler, event, data):
        if not self.initialized:
            await self.db.create_indexes()
            # await self.db.currency_converter.init_session()
            self.initialized = True

        user_id = data["event_from_user"].id

        customer = await self.db.customers.get_customer_by_id(user_id)

        ### remove when redo funcs that depends                              |
        data["lang"] = customer.lang if customer and customer.lang else "?"# |
        ###                                                                  |
        data["middleware"] = self #                                          |
        data["db"] = self.db #                                               |
        ### remove when redo funcs that depends                              |

        data["ctx"] = Context(event.message or event.callback_query,
                              data.get("state"),
                              self.db,
                              customer,
                              data["lang"])

        if not customer and not await data.get("state").get_state() == NewUserStates.LangChoosing:
            await data["ctx"].fsm.set_state(NewUserStates.LangChoosing)
            return await data["ctx"].message.answer("Account deleted. Enter /start.", reply_keyboard=ReplyKeyboardRemove())

        return await handler(event, data)

class ThrottlingMiddleware(BaseMiddleware):
    default = TTLCache(maxsize=25_000, ttl=.25)
    # Храним временные метки запросов пользователя (user_id -> [timestamps])
    user_requests = TTLCache(maxsize=25_000, ttl=30)
    # Храним "забаненных" пользователей (user_id -> время окончания бана)
    banned_users = TTLCache(maxsize=25_000, ttl=15)

    async def __call__(
            self,
            handler,
            event,
            data
    ) -> Any:
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