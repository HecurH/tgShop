from typing import Dict, Optional

from aiogram import Dispatcher
from aiogram.types import TelegramObject, CallbackQuery, update
from pymongo import MongoClient
from src.classes.db import DB



class MongoDBMiddleware:
    def __init__(self):
        self.db = DB()
        self.langs: Dict[int, str] = {}

    async def __call__(self, handler, event, data):
        user_id = data["event_from_user"].id

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
        data["middleware"] = self
        data["db"] = self.db
        return await handler(event, data)


    def update_customer_cache(self, user_id: int, lang: str):
        self.langs[user_id] = lang