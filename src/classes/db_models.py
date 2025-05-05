import datetime
from typing import Optional, Any

from pydantic import BaseModel
from pydantic_mongo import AsyncAbstractRepository, PydanticObjectId


class Order(BaseModel):
    id: Optional[PydanticObjectId] = None
    name: str

    configurations: dict[str, dict[str, Any]]


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

    lang: str

    # def get_updateable(self, db: "DB") -> Updateable:
    #     return db.get_updateable(self.updateable_id)

class CustomersRepository(AsyncAbstractRepository[Customer]):
    class Meta:
        collection_name = 'customers'
