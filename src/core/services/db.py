import asyncio
import logging

import pymongo
from pymongo import AsyncMongoClient

from configs.environment import MONGO_URI, MONGO_TLS_CA_PATH, MONGO_TLS_KEY_PATH
from schemas.db_models import *

class DatabaseService:
    def __init__(self, db_name="Shop"):
        self.client = AsyncMongoClient(MONGO_URI, 
                                       tls=True,
                                       tlsCAFile=MONGO_TLS_CA_PATH,
                                       tlsCertificateKeyFile=MONGO_TLS_KEY_PATH)
        self.db = self.client.get_database(db_name)
        
        self.collections: dict[str, AppAbstractRepository] = {
            "logs": LogsRepository,
            "placeholders": PlaceholdersRepository,
            "orders": OrdersRepository,
            "cart_entries": CartEntriesRepository,
            "delivery_services": DeliveryServicesRepository,
            "customers": CustomersRepository,
            "products": ProductsRepository,
            "discounted_products": DiscountedProductsRepository,
            "additionals": AdditionalsRepository,
            "categories": CategoriesRepository,
            "inviters": InvitersRepository,
            "promocodes": PromocodesRepository
        }

        self._init_collections()
        
        logging.getLogger(__name__).info("Database service initialized.")

    def _init_collections(self):
        for key, repo_class in self.collections.items():
            instance = repo_class(self)
            
            self.collections[key] = instance
            setattr(self, key, instance)

    async def _create_indexes(self):
        await self.db["placeholders"].create_index([("key", pymongo.ASCENDING)], unique=True)
        
        await self.db["orders"].create_index([("customer_id", pymongo.ASCENDING)])
        await self.db["orders"].create_index([("number", pymongo.ASCENDING)], unique=True)

        await self.db["cart_entries"].create_index([("customer_id", pymongo.ASCENDING)])

        await self.db["customers"].create_index([("user_id", pymongo.ASCENDING)], unique=True)

        await self.db["categories"].create_index([("name", pymongo.ASCENDING)], unique=True)

        await self.db["inviters"].create_index([("customer_id", pymongo.ASCENDING)], unique=True)

        await self.db["promocodes"].create_index([("code", pymongo.ASCENDING)], unique=True)
        
    async def _check_migrations(self):
        semaphore = asyncio.Semaphore(3)
        
        async def check_with_semaphore(repo):
            async with semaphore:
                return await repo.check_migrations()
        
        tasks = [check_with_semaphore(repo) for repo in self.collections.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        errors = [r for r in results if isinstance(r, Exception)]
        
        if errors:
            for e in errors:
                logging.getLogger(__name__).critical(f"Migration failed: {e}")
            raise errors[0]
        

    async def prepare(self):
        await self._create_indexes()
        await self._check_migrations()
        

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
        logging.getLogger(__name__).info("Database service closed.")