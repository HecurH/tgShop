from os import getenv

import pymongo
from pymongo import AsyncMongoClient

from schemas.db_models import *

class DatabaseService:
    def __init__(self, db_name="Shop"):
        self.client = AsyncMongoClient(getenv("MONGO_URI"), tls=True, tlsAllowInvalidCertificates=True, tlsCAFile=getenv("MONGO_TLS_CA_PATH"))
        self.db = self.client.get_database(db_name)

        self._init_collections()

    def _init_collections(self):
        self.placeholders = PlaceholdersRepository(self)
        self.orders = OrdersRepository(self)
        self.cart_entries = CartEntriesRepository(self)
        self.delivery_services = DeliveryServicesRepository(self)
        self.customers = CustomersRepository(self)
        self.products = ProductsRepository(self)
        self.additionals = AdditionalsRepository(self)
        self.categories = CategoriesRepository(self)
        self.inviters = InvitersRepository(self)
        self.promocodes = PromocodesRepository(self)

    async def create_indexes(self):
        await self.db["placeholders"].create_index([("key", pymongo.ASCENDING)], unique=True)
        
        await self.db["orders"].create_index([("customer_id", pymongo.ASCENDING)])
        await self.db["orders"].create_index([("number", pymongo.ASCENDING)], unique=True)

        await self.db["cart_entries"].create_index([("customer_id", pymongo.ASCENDING)])

        await self.db["customers"].create_index([("user_id", pymongo.ASCENDING)], unique=True)

        await self.db["categories"].create_index([("name", pymongo.ASCENDING)], unique=True)

        await self.db["inviters"].create_index([("customer_id", pymongo.ASCENDING)], unique=True)

        await self.db["promocodes"].create_index([("code", pymongo.ASCENDING)], unique=True)

    async def get_next_for_counter(self, name):

        counter = await self.db.counters.find_one_and_update(
            {"name": name},
            {"$inc": {"value": 1}},
            upsert=True,
            return_document=True
        )

        return counter["value"]
    
    async def close(self):
        await self.client.close()