from typing import Dict, Optional

from aiogram import Dispatcher
from aiogram.types import TelegramObject
from pymongo import MongoClient
from src.classes.db import DB



class MongoDBMiddleware:
    def __init__(self):
        self.db = DB()
        self.langs: Dict[int, str] = {}

    async def __call__(self, handler, event, data):
        user_id = self._extract_user_id(event)

        if user_id:
            # Проверяем кеш
            if user_id not in self.langs:
                # Если нет в кеше - загружаем из БД
                customer = await self.db.get_user_by_id(user_id)
                if customer:
                    self.langs[user_id] = customer.lang
                else:
                    self.langs[user_id] = "?"


            # Добавляем пользователя в контекст
            if user_id in self.langs:
                data["lang"] = self.langs[user_id]
            data["db_middleware"] = self
            data["db"] = self.db
        return await handler(event, data)

    def _extract_user_id(self, event: TelegramObject) -> Optional[int]:
        # Извлекаем user_id из различных типов событий
        if hasattr(event, 'from_user') and event.from_user:
            return event.from_user.id
        if hasattr(event, 'message') and event.message:
            return event.message.from_user.id
        return None

    def update_customer_cache(self, user_id: int, lang: str):
        self.langs[user_id] = lang