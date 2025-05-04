from aiogram import Dispatcher
from pymongo import MongoClient



class MongoDBMiddleware:
    def __init__(self):
        self.client = MongoClient(mongo_uri)

    async def __call__(self, handler, event, data):
        data["db"] = self.db
        return await handler(event, data)