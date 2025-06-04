from typing import Any

from aiogram import BaseMiddleware
from cachetools import TTLCache

from src.classes.db import DB


class MongoDBMiddleware(BaseMiddleware):
    def __init__(self):
        self.db = DB()
        self.initialized = False

    async def __call__(self, handler, event, data):
        if not self.initialized:
            await self.db.create_indexes()
            self.initialized = True

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

class RoleCheckMiddleware(BaseMiddleware):
    def __init__(self, allowed: list[str] | str):
        self.allowed = allowed

    async def __call__(self, handler, event, data):
        db: DB = data["db"]
        user = await db.customers.get_user_by_id(data["event_from_user"].id)


        if (not db or
                not user or
                ((user.role != self.allowed) if isinstance(self.allowed, str) else (user.role in self.allowed))):

            return

        return await handler(event, data)