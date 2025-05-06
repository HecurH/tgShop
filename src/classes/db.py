import datetime
from os import getenv
from typing import Optional, Type, TypeVar, Iterable, Any, List, Union
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError
import logging

from src.classes.db_models import *

T = TypeVar("T", bound="MongoModel")



class DB:
    """
    Класс для управления базой данных
    """

    def __init__(self, db_name="Shop"):
        self.client = AsyncMongoClient(getenv("MONGO_URI"))
        self.db = self.client[db_name]
        self.logger = logging.getLogger(__name__)
        self._init_collections()

    def _init_collections(self):
        self.cart_entries = CartEntriesRepository(self.db)
        self.customers = CustomersRepository(self.db)
        self.products = ProductsRepository(self.db)
        self.inviters = InvitersRepository(self.db)
        self.promocodes = PromocodesRepository(self.db)

    # def get_updateable(self, updateable_id: PydanticObjectId) -> Optional[Updateable]:
    #     return self.get(Updateable, updateable_id)

    async def get_by_id(self, model: Type[T], entity_id: PydanticObjectId) -> Optional[T]:
        try:
            collection = self._get_collection(model)
            doc = await collection.find_one_by_id(entity_id)
            return doc if doc else None
        except PyMongoError as e:
            self._handle_error(e)
            return None

    async def get_by_query(self, model: Type[T], query: dict) -> Optional[Iterable[T]]:
        try:
            collection = self._get_collection(model)
            doc = await collection.find_by(query)
            return doc if doc else None
        except PyMongoError as e:
            self._handle_error(e)
            return None

    async def get_count_by_query(self, model: Type[T], query: dict) -> int | None:
        try:
            collection = self._get_collection(model).Meta.collection_name

            return await self.db[collection].count_documents(query)
        except PyMongoError as e:
            self._handle_error(e)
            return None

    async def get_one_by_query(self, model: Type[T], query: dict) -> Optional[T]:
        try:
            collection = self._get_collection(model)
            doc = await collection.find_one_by(query)
            return doc if doc else None
        except PyMongoError as e:
            self._handle_error(e)
            return None

    async def insert(self, entities: Union[T, list[T]]) -> Union[T, list[T]]:
        try:
            if isinstance(entities, list):
                if not entities:
                    return []
                collection = self._get_collection(type(entities[0]))
                result = await collection.save_many(entities)
                # Assign inserted IDs to each entity in the list
                for entity, inserted_id in zip(entities, result.inserted_ids):
                    entity.id = inserted_id
                return entities
            else:
                collection = self._get_collection(type(entities))
                result = await collection.save(entities)
                entities.id = result.inserted_id
                return entities
        except PyMongoError as e:
            self._handle_error(e)
            raise

    async def delete(self, entity: T) -> bool:
        try:
            if not entity.id:
                raise ValueError("Entity must have an id to be deleted")

            collection = self._get_collection(type(entity))
            result = await collection.delete_by_id(entity.id)

            return result.deleted_count > 0

        except PyMongoError as e:
            self._handle_error(e)
            raise

    async def update(self, entity: T) -> bool:
        try:
            if not entity.id:
                raise ValueError("Entity must have an id to be updated")
            collection = self._get_collection(type(entity))
            updated = await collection.save(
                entity
            )
            return updated.modified_count > 0
        except PyMongoError as e:
            self._handle_error(e)
            return False

    def _get_collection(self, model: Type[T]):
        if model == CartEntry:
            return self.cart_entries
        if model == Customer:
            return self.customers
        if model == Product:
            return self.products
        if model == Inviter:
            return self.inviters
        if model == Promocode:
            return self.promocodes
        raise ValueError(f"No collection for model {model.__name__}")

    # Специфичные методы
    async def get_user_by_id(self, user_id: int) -> Optional[Customer]:
        try:
            doc = await self.customers.find_one_by({"user_id": user_id})

            return doc if doc else None
        except PyMongoError as e:
            self._handle_error(e)
            return None


    # def get_posts(self, query: dict) -> Optional[Iterable[Post]]:
    #     try:
    #         docs = self.posts.find_by(query)
    #         return docs if docs else None
    #     except PyMongoError as e:
    #         self._handle_error(e)
    #         return None

    # def get_count_by_updateable(self, updateable: Updateable) -> int | None:
    #     try:
    #         return self.db['posts'].count_documents({"updateable_id": str(updateable.id), "deleted": False})
    #     except PyMongoError as e:
    #         self._handle_error(e)
    #         return None
    #
    # def get_updateables(self) -> Iterable[Updateable] | None:
    #     try:
    #         docs = self.updateables.find_by({})
    #         return docs
    #     except PyMongoError as e:
    #         self._handle_error(e)
    #         return None
    #
    # def get_blacklist(self) -> list[str] | None:
    #     try:
    #         docs = self.blacklist.find_by({})
    #         return [doc.name for doc in list(docs)]
    #     except PyMongoError as e:
    #         self._handle_error(e)
    #         return None

    def _handle_error(self, error: PyMongoError):
        self.logger.error(f"Database error: {error}")