from typing import Dict, Optional, Callable, Awaitable, Any

from aiogram import BaseMiddleware
from aiogram.types import Message
from cachetools import TTLCache

from src.classes.db import DB


class MongoDBMiddleware(BaseMiddleware):
    def __init__(self):
        self.db = DB()

    async def __call__(self, handler, event, data):
        user_id = data["event_from_user"].id

        user = await self.db.customers.get_user_by_id(user_id)
        data["lang"] = user.lang if user and user.lang else "?"

        data["middleware"] = self
        data["db"] = self.db
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