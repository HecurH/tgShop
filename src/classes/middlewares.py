from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import ReplyKeyboardRemove
from cachetools import TTLCache

from src.classes.db import DB
from src.classes.helper_classes import Context, AsyncCurrencyConverter
from src.classes.states import CommonStates, call_state_handler


class ContextMiddleware(BaseMiddleware):
    def __init__(self):
        self.db = DB()
        self.db_initialized = False

    async def __call__(self, handler, event, data):
        if not self.db_initialized:
            await self.db.create_indexes()
            await self.db.currency_converter.init_session()
            self.initialized = True

        user_id = data["event_from_user"].id

        customer = await self.db.customers.get_customer_by_id(user_id)

        ### remove when redo funcs that depends
        data["lang"] = customer.lang if customer and customer.lang else "?"

        data["middleware"] = self
        data["db"] = self.db
        ### remove when redo funcs that depends

        data["ctx"] = Context(event.message or event.callback_query,
                              data.get("state"),
                              self.db,
                              customer,
                              data["lang"])

        if not customer and not await data.get("state").get_state() == CommonStates.lang_choosing:
            await data["ctx"].fsm.set_state(CommonStates.lang_choosing)
            return await data["ctx"].message.answer("Account deleted. Enter /start.", reply_keyboard=ReplyKeyboardRemove())

        return await handler(event, data)


class ThrottlingMiddleware(BaseMiddleware):
    default = TTLCache(maxsize=10_000, ttl=.25)

    async def __call__(
            self,
            handler,
            event,
            data
    ) -> Any:
        if data["event_from_user"].id in self.default:
            return
        else:
            self.default[data["event_from_user"].id] = None
        return await handler(event, data)

class RoleCheckMiddleware(BaseMiddleware):
    def __init__(self, allowed: list[str] | str):
        self.allowed = allowed

    async def __call__(self, handler, event, data):
        db: DB = data["db"]
        user = await db.customers.get_customer_by_id(data["event_from_user"].id)


        if (not db or
                not user or
                ((user.role != self.allowed) if isinstance(self.allowed, str) else (user.role in self.allowed))):

            return

        return await handler(event, data)