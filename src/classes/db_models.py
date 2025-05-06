import datetime
from typing import Optional, Any, List, Iterable

from pydantic import BaseModel
from pydantic_mongo import AsyncAbstractRepository, PydanticObjectId

from src.classes.db import DB


class Order(BaseModel):
    id: Optional[PydanticObjectId] = None
    customer_id: PydanticObjectId
    product_id: PydanticObjectId
    step: str

    configuration: dict[Any]
    colors: str

    promocodes: List[PydanticObjectId]



class OrdersRepository(AsyncAbstractRepository[Order]):
    class Meta:
        collection_name = 'orders'

class Product(BaseModel):
    id: Optional[PydanticObjectId] = None
    name: str

    configurations: dict[str, dict[str, Any]]

    # {
    #     "Размер": {
    #         "text": "Выберите размер товара:",
    #         "choices": [
    #             ["Маленький", False],
    #             ["Средний", False],
    #             ["Большой", False]
    #         ]
    #     },
    #     "Твёрдость": {
    #         "text": "Выберите твёрдость товара:",
    #         "choices": [
    #             ["Мягкий", False],
    #             ["Средний", False],
    #             ["Твёрдый", False]
    #         ]
    #     },
    #     "Расцветка": {
    #         "text": "Выберите расцветку товара:",
    #         "choices": [
    #             ["Оригинальный", False],
    #             ["Шоколадный", False],
    #             ["Свой вариант", True]
    #         ]
    #     }
    # }

class ProductsRepository(AsyncAbstractRepository[Product]):
    class Meta:
        collection_name = 'products'


class Promocode(BaseModel):
    id: Optional[PydanticObjectId] = None
    code: str
    only_newbies: bool
    product_restriction: list[PydanticObjectId]

    already_used: int = 0
    max_usages: int = -1

    expire_date: datetime.datetime


    # # Метод для получения связанного документа
    # def get_updateable(self, db: "DB") -> Updateable:
    #     return db.get_updateable(self.updateable_id)

class PromocodesRepository(AsyncAbstractRepository[Promocode]):
    class Meta:
        collection_name = 'promocodes'


class Inviter(BaseModel):
    id: Optional[PydanticObjectId] = None
    inviter_code: str

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

    invited_by: str
    kicked: bool = False

    lang: str

    async def get_orders(self, db: DB) -> Iterable[Order]:

        return await db.get_by_query(Order, {"customer_id": self.user_id})

class CustomersRepository(AsyncAbstractRepository[Customer]):
    class Meta:
        collection_name = 'customers'
