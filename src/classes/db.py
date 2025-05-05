import datetime
from os import getenv
from typing import Optional, Type, TypeVar, Iterable
from pydantic import BaseModel
from pydantic_mongo import PydanticObjectId, AsyncAbstractRepository
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import logging

T = TypeVar("T", bound="MongoModel")


class BlacklistTag(BaseModel):
    id: Optional[PydanticObjectId] = None,
    name: str



class BlacklistRepository(AbstractRepository[BlacklistTag]):
    class Meta:
        collection_name = 'blacklist'


class Updateable(BaseModel):
    id: Optional[PydanticObjectId] = None,
    name: str
    blacklist: list[str]
    path: str


class UpdateablesRepository(AbstractRepository[Updateable]):
    class Meta:
        collection_name = 'updateables'


# Класс для хранения данных о постах
class Post(BaseModel):
    id: Optional[PydanticObjectId] = None
    updateable_id: PydanticObjectId  # Ссылка на Updateable через ID
    tags: list[str]
    source: str
    deleted: bool
    filename: str

    # Метод для получения связанного документа
    def get_updateable(self, db: "DB") -> Updateable:
        return db.get_updateable(self.updateable_id)


class PostsRepository(AbstractRepository[Post]):
    class Meta:
        collection_name = 'posts'

class Promocode(BaseModel):
    id: Optional[PydanticObjectId] = None
    code: str
    only_newbies: bool

    already_used: int = 0
    max_usages: int

    expire_date: datetime.datetime


    # # Метод для получения связанного документа
    # def get_updateable(self, db: "DB") -> Updateable:
    #     return db.get_updateable(self.updateable_id)

class PromocodesRepository(AsyncAbstractRepository[Promocode]):
    class Meta:
        collection_name = 'promocodes'


class Inviter(BaseModel):
    id: Optional[PydanticObjectId] = None
    inviter_code: int

    name: str


    # # Метод для получения связанного документа
    # def get_updateable(self, db: "DB") -> Updateable:
    #     return db.get_updateable(self.updateable_id)

class InvitersRepository(AsyncAbstractRepository[Inviter]):
    class Meta:
        collection_name = 'inviters'


class Customer(BaseModel):
    id: Optional[PydanticObjectId] = None
    user_id: int

    invited_by: int
    kicked: bool = False


    # # Метод для получения связанного документа
    # def get_updateable(self, db: "DB") -> Updateable:
    #     return db.get_updateable(self.updateable_id)

class CustomersRepository(AsyncAbstractRepository[Customer]):
    class Meta:
        collection_name = 'customers'


class DB:
    """
    Класс для управления базой данных
    """

    def __init__(self, db_name="Shop"):
        self.client = MongoClient(getenv("MONGO_URI"))
        self.db = self.client[db_name]
        self.logger = logging.getLogger(__name__)
        self._init_collections()

    def _init_collections(self):
        self.posts = PostsRepository(self.db)
        self.updateables = UpdateablesRepository(self.db)
        self.blacklist = BlacklistRepository(self.db)

    def get_updateable(self, updateable_id: PydanticObjectId) -> Optional[Updateable]:
        return self.get(Updateable, updateable_id)

    def get(self, model: Type[T], entity_id: PydanticObjectId) -> Optional[T]:
        try:
            collection = self._get_collection(model)
            doc = collection.find_one_by_id(entity_id)
            return doc if doc else None
        except PyMongoError as e:
            self._handle_error(e)
            return None

    def insert(self, entity: T) -> T:
        try:
            collection = self._get_collection(type(entity))
            result = collection.save(entity)
            entity.id = result.inserted_id
            return entity
        except PyMongoError as e:
            self._handle_error(e)
            raise

    def insert_many(self, entities: list[T]) -> None:
        try:
            collection = self._get_collection(type(entities[0]))
            result = collection.save_many(entities)
        except PyMongoError as e:
            self._handle_error(e)
            raise

    def delete(self, entity: T) -> bool:
        try:
            if not entity.id:
                raise ValueError("Entity must have an id to be deleted")

            collection = self._get_collection(type(entity))
            result = collection.delete_by_id(entity.id)

            return result.deleted_count > 0

        except PyMongoError as e:
            self._handle_error(e)
            raise

    def update(self, entity: T) -> bool:
        try:
            if not entity.id:
                raise ValueError("Entity must have an id to be updated")
            collection = self._get_collection(type(entity))
            updated = collection.save(
                entity
            )
            return updated.modified_count > 0
        except PyMongoError as e:
            self._handle_error(e)
            return False

    def _get_collection(self, model: Type[T]):
        if model == Post:
            return self.posts
        if model == Updateable:
            return self.updateables
        if model == BlacklistTag:
            return self.blacklist
        raise ValueError(f"No collection for model {model.__name__}")

    # Специфичные методы
    def get_post(self, filename: str, updateable: Updateable) -> Optional[Post]:
        try:
            doc = self.posts.find_one_by({"updateable_id": str(updateable.id), "filename": filename})

            return doc if doc else None
        except PyMongoError as e:
            self._handle_error(e)
            return None

    def get_posts(self, query: dict) -> Optional[Iterable[Post]]:
        try:
            docs = self.posts.find_by(query)
            return docs if docs else None
        except PyMongoError as e:
            self._handle_error(e)
            return None

    def get_count_by_updateable(self, updateable: Updateable) -> int | None:
        try:
            return self.db['posts'].count_documents({"updateable_id": str(updateable.id), "deleted": False})
        except PyMongoError as e:
            self._handle_error(e)
            return None

    def get_updateables(self) -> Iterable[Updateable] | None:
        try:
            docs = self.updateables.find_by({})
            return docs
        except PyMongoError as e:
            self._handle_error(e)
            return None

    def get_blacklist(self) -> list[str] | None:
        try:
            docs = self.blacklist.find_by({})
            return [doc.name for doc in list(docs)]
        except PyMongoError as e:
            self._handle_error(e)
            return None

    def _handle_error(self, error: PyMongoError):
        self.logger.error(f"Database error: {error}")