from aiogram import Dispatcher
from pymongo import MongoClient
from src.classes.db import DB



class MongoDBMiddleware:
    def __init__(self):
        self.db = DB()

    async def __call__(self, handler, event, data):
        data["db"] = self.db
        return await handler(event, data)