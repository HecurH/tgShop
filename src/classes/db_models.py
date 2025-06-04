import datetime
import logging
from typing import Optional, List, Iterable, TYPE_CHECKING

from pydantic import BaseModel, Field
from pydantic_mongo import AsyncAbstractRepository, PydanticObjectId
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

if TYPE_CHECKING:
    from db import DB

class Order(BaseModel):
    id: Optional[PydanticObjectId] = None
    customer_id: PydanticObjectId
    promocodes: list[PydanticObjectId]

    entries: list[PydanticObjectId]

    async def add_promocode(self, promocode: "Promocode", db: "DB") -> Optional[bool]:
        user: "Customer" = await db.get_by_id(Customer, self.customer_id)
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
    need_to_confirm_price: bool = False

    quantity: int = Field(default=1, gt=0)

    configuration: "ProductConfiguration"

class CartEntriesRepository(AsyncAbstractRepository[CartEntry]):
    class Meta:
        collection_name = 'cart_entries'

class LocalizedString(BaseModel):
    data: dict[str, str]

class LocalizedPrice(BaseModel):
    data: dict[str, float]

class ConfigurationSwitch(BaseModel):
    name: LocalizedString
    price: LocalizedPrice = Field(default_factory=lambda: LocalizedPrice(data={"ru": 0, "en": 0}))


    enabled: bool = False

class ConfigurationSwitches(BaseModel):
    label: LocalizedString
    description: LocalizedString
    photo_id: Optional[str] = None
    video_id: Optional[str] = None

    switches: list[ConfigurationSwitch]

    def get_enabled(self):
        return [switch for switch in self.switches if switch.enabled]

    @staticmethod
    def calculate_price(switches: list[ConfigurationSwitch], lang):
        return sum([switch.price.data[lang] for switch in switches])

class ConfigurationChoice(BaseModel):
    label: LocalizedString
    description: LocalizedString
    photo_id: Optional[str] = None
    video_id: Optional[str] = None

    existing_presets: bool = Field(default=False)
    existing_presets_chosen: int = 1
    existing_presets_quantity: int = 0

    is_custom_input: bool = Field(default=False)
    custom_input_text: Optional[str] = None
    price: LocalizedPrice = Field(default_factory=lambda: LocalizedPrice(data={"ru": 0, "en": 0}))

class ConfigurationOption(BaseModel):
    name: LocalizedString
    text: LocalizedString
    photo_id: Optional[str] = None
    video_id: Optional[str] = None
    chosen: int

    choices: List[ConfigurationChoice | ConfigurationSwitches]

class ProductConfiguration(BaseModel):
    options: dict[str, ConfigurationOption]
    additionals: list["ProductAdditional"] = []


class Product(BaseModel):
    id: Optional[PydanticObjectId] = None
    order_no: int = None
    name: LocalizedString
    category: str

    short_description: LocalizedString
    short_description_photo_id: str

    long_description: LocalizedString
    long_description_photo_id: str

    base_price: LocalizedPrice

    configuration_photo_id: Optional[str] = None
    configuration_video_id: Optional[str] = None
    configuration: ProductConfiguration

class ProductsRepository(AsyncAbstractRepository[Product]):
    class Meta:
        collection_name = 'products'

    async def insert(self, model: Product, category, db: "DB"):
        model.order_no = await db.get_counter(category)
        await self.save(model)

class ProductAdditional(BaseModel):
    id: Optional[PydanticObjectId] = None
    name: LocalizedString
    category: str

    short_description: LocalizedString

    price: LocalizedPrice
    disallowed_products: list[PydanticObjectId] = []


class AdditionalsRepository(AsyncAbstractRepository[ProductAdditional]):
    class Meta:
        collection_name = 'additionals'

    async def get(self, category: str, product_id: PydanticObjectId):
        return await self.find_by({"category": category, "disallowed_products": {"$nin": [str(product_id)]}})




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
    role: str = "default"

    invited_by: str
    kicked: bool = False

    lang: str

    async def get_cart(self, db: "DB") -> Iterable[CartEntry]:
        return await db.get_by_query(CartEntry, {"customer_id": self.id})

    async def get_orders(self, db: "DB") -> Iterable[Order]:
        return await db.get_by_query(Order, {"customer_id": self.id})

    async def add_to_cart(self, db: "DB", product: Product,
                          configuration: ProductConfiguration):

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
    localized_name: LocalizedString


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