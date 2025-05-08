import datetime
import logging
from typing import Optional, Any, List, Iterable

from pydantic import BaseModel, Field
from pydantic_mongo import AsyncAbstractRepository, PydanticObjectId
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError


class Order(BaseModel):
    id: Optional[PydanticObjectId] = None
    customer_id: PydanticObjectId
    promocodes: list[PydanticObjectId]

    entries: list[PydanticObjectId]

    async def add_promocode(self, promocode: "Promocode", db: "DB") -> Optional[bool]:
        user: "Customer" = await db.get_user_by_id(self.customer_id)
        if promocode.only_newbies:
            count = await db.get_count_by_query(Order, {"customer_id": self.customer_id})
            if count != 0:
                return False



class OrdersRepository(AsyncAbstractRepository[Order]):
    class Meta:
        collection_name = 'orders'

class CartEntry(BaseModel):
    id: Optional[PydanticObjectId] = None
    customer_id: PydanticObjectId
    product_id: PydanticObjectId
    in_order: bool = False

    quantity: int = Field(default=1, gt=0)

    configuration: dict[Any, Any]

class CartEntriesRepository(AsyncAbstractRepository[CartEntry]):
    class Meta:
        collection_name = 'cart_entries'


class Product(BaseModel):
    id: Optional[PydanticObjectId] = None
    name: str
    category: str

    base_price: int

    configurations: dict[str, dict[str, Any]]

    # d = {
    #     "Размер": {
    #         "text": {"ru": "Выберите размер товара:", "en": "Choose the size of the product:"},
    #         "choices": [
    #             ["Маленький", False, -n],
    #             ["Средний", False, 0],
    #             ["Большой", False, n]
    #         ]
    #     },
    #     "Твёрдость": {
    #         "text": {"ru": "Выберите твёрдость изделия:", "en": "Choose the hardness of the product:"},
    #         "choices": [
    #             ["Мягкий", False, 0],
    #             ["Средний", False, 0],
    #             ["Твёрдый", False, 0]
    #         ]
    #     },
    #     "Расцветка": {
    #         "text": {"ru": "Выберите расцветку товара:", "en": "Choose the color of the product:"},
    #         "choices": [
    #             ["Оригинальный", False, 0],
    #             ["Шоколадный", False, 0],
    #             ["Свой вариант", True, 0]
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

    async def get_cart(self, db: "DB") -> Iterable[CartEntry]:
        return await db.get_by_query(CartEntry, {"customer_id": self.id})

    async def get_orders(self, db: "DB") -> Iterable[Order]:
        return await db.get_by_query(Order, {"customer_id": self.id})

    async def add_to_cart(self, db: "DB", product: Product,
                          configuration: dict):

        # Проверка на существующую запись
        existing = await db.get_one_by_query(CartEntry, {
            "customer_id": self.id,
            "product_id": product.id,
            "configuration": configuration
        })

        if existing:
            existing.quantity += 1
            await db.update(existing)
            return existing

        new_entry = CartEntry(
            customer_id=self.id,
            product_id=product.id,
            configuration=configuration
        )
        return await db.insert(new_entry)


class CustomersRepository(AsyncAbstractRepository[Customer]):
    class Meta:
        collection_name = 'customers'

    def __init__(self, database: AsyncDatabase):
        super().__init__(database)
        self.logger = logging.getLogger(__name__)


    async def get_user_by_id(self, user_id: int) -> Optional[Customer]:
        try:
            doc = await self.find_one_by({"user_id": user_id})

            return doc if doc else None
        except PyMongoError as e:
            handle_error(self.logger, e)


class Category(BaseModel):
    id: Optional[PydanticObjectId] = None
    name: str

class CategoriesRepository(AsyncAbstractRepository[Category]):
    class Meta:
        collection_name = 'categories'

    def __init__(self, database: AsyncDatabase):
        super().__init__(database)
        self.logger = logging.getLogger(__name__)


    async def get_all(self) -> Optional[Iterable[Category]]:
        try:
            doc = await self.find_by({})

            return doc if doc else None
        except PyMongoError as e:
            handle_error(self.logger, e)

def handle_error(logger, error: PyMongoError):
    logger.error(f"Database error: {error}")