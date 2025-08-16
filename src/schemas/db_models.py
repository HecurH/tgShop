import datetime
import logging
from typing import Any, Dict, TypeVar, Optional, List, Iterable, TYPE_CHECKING

from pydantic import BaseModel, Field
from pydantic_mongo import AsyncAbstractRepository, PydanticObjectId
from pymongo.errors import PyMongoError

from configs.supported import SUPPORTED_CURRENCIES
from core.helper_classes import AsyncCurrencyConverter
from schemas.db_schemas import DeliveryInfo, DeliveryRequirementsList, ProductConfiguration
from schemas.enums import PromocodeCheckResult, OrderState
from schemas.payment_models import PaymentMethod
from schemas.types import LocalizedMoney, LocalizedString, Money, OrderState, PromocodeAction

if TYPE_CHECKING:
    from core.db import DatabaseService

T = TypeVar("T")

class AppAbstractRepository(AsyncAbstractRepository[T]):
    def __init__(self, dbs: "DatabaseService"):
        super().__init__(dbs.db)
        self.dbs = dbs
    
class OrderPriceDetails(BaseModel):
    products_price: Money  # сумма товаров без скидок и доставки
    promocode_discount: Optional[Money] = None  # скидка по промокоду
    
    delivery_price: Money  # доставка
    bonuses_applied: Optional[Money] = None # сколько бонусных средств для оплаты
    
    total_price: Money  # сколько надо заплатить настоящими деньгами
    paid_total: Optional[Money] = None  # сколько всего заплатил пользователь
    
    def recalculate_price(self):
        products_price_after_promocode = (self.products_price - self.promocode_discount) if self.promocode_discount else self.products_price
        self.total_price = products_price_after_promocode + self.delivery_price - self.bonuses_applied
    
class Order(BaseModel):
    id: Optional[PydanticObjectId] = None
    customer_id: PydanticObjectId
    state: OrderState = OrderState(OrderState.forming)
    delivery_info: Optional[DeliveryInfo] = None # при запросе удаления перс данных, обычно не должен быть пуст

    promocode: Optional[PydanticObjectId] = None

    price_details: OrderPriceDetails
    payment_method: Optional[PaymentMethod] = None

    async def set_promocode(self, promocode: Optional["Promocode"]):
        self.price_details.promocode_discount = promocode.action.get_discount(self.price_details.products_price) if promocode else None
        self.price_details.recalculate_price()
    
    async def update_applied_bonuses(self, customer_bonus_balance: Money):
        self.price_details.bonuses_applied = min(self.price_details.bonuses_applied, customer_bonus_balance)

class OrdersRepository(AppAbstractRepository[Order]):
    class Meta:
        collection_name = 'orders'
        
    def new_order(self, customer: "Customer", products_price: LocalizedMoney) -> Order:
        delivery_info = customer.delivery_info
        currency = customer.currency
        
        price_details = OrderPriceDetails(products_price=products_price.get_money(),
                                          delivery_price=delivery_info.service.price.get_money(currency)
                                          )
        price_details.recalculate_price()
        
        return Order(customer_id=customer.id, delivery_info=delivery_info, price_details=price_details)

class CartEntry(BaseModel):
    id: Optional[PydanticObjectId] = None
    customer_id: PydanticObjectId
    product_id: PydanticObjectId
    order_id: Optional[PydanticObjectId] = None

    quantity: int = Field(default=1, gt=0)

    configuration: "ProductConfiguration"
    
    @property
    def need_to_confirm_price(self) -> bool:
        return any(
            hasattr(option.choices[option.chosen - 1], "blocks_price_determination") and
            option.choices[option.chosen - 1].blocks_price_determination
            for option in self.configuration.options
        )

class CartEntriesRepository(AppAbstractRepository[CartEntry]):
    class Meta:
        collection_name = 'cart_entries'
    
    async def add_to_cart(self, product: "Product", customer: "Customer"):
        await self.save(CartEntry(customer_id=customer.id, 
                      product_id=product.id, 
                      configuration=product.configuration))
        
    async def count_customer_cart_entries(self, customer: "Customer"):
        return await self.get_collection().count_documents({"customer_id": customer.id, "order_id": None})
    
    async def get_customer_cart_ids_by_customer_sorted_by_date(self, customer: "Customer") -> List[PydanticObjectId]:
        """Получить список id продуктов в категории, отсортированных по дате создания (ObjectId)."""
        cursor = self.get_collection().find(
            {"customer_id": customer.id,
             "order_id": None},
            projection={"_id": 1}
        ).sort("_id", 1)
        return [PydanticObjectId(doc["_id"]) async for doc in cursor]

    async def get_customer_cart_entry_by_id(self, customer: "Customer", idx: int) -> CartEntry:
        ids = await self.get_customer_cart_ids_by_customer_sorted_by_date(customer)
        return await self.find_one_by_id(ids[idx])
    
    async def calculate_customer_cart_price(self, customer: "Customer") -> LocalizedMoney:
        # sourcery skip: comprehension-to-generator
        entries: Iterable[CartEntry] = await self.find_by({"customer_id": customer.id, "order_id": None})
        return sum(
            [
                (((await self.dbs.products.find_one_by_id(entry.product_id)).base_price + entry.configuration.price) * entry.quantity)
                for entry in entries
            ],
            LocalizedMoney()
        )
    
class Product(BaseModel):
    id: Optional[PydanticObjectId] = None
    name: LocalizedString
    category: str

    short_description: LocalizedString
    short_description_photo_id: str

    long_description: LocalizedString
    long_description_photo_id: Optional[str] = None
    long_description_video_id: Optional[str] = None

    base_price: LocalizedMoney

    configuration_photo_id: Optional[str] = None
    configuration_video_id: Optional[str] = None
    configuration: ProductConfiguration
    
    
    # def calculate_price(self, configuration: ProductConfiguration = None) -> LocalizedPrice:
    #     total_price = self.base_price.model_copy(deep=True)
    #     configuration = configuration or self.configuration
        
    #     for option in configuration.options.values():
    #         total_price += option.calculate_price()
            
    #     if len(configuration.additionals) > 0:
    #         total_price += configuration.calculate_additionals_price()
            
    #     return total_price

class ProductsRepository(AppAbstractRepository[Product]):
    class Meta:
        collection_name = 'products'
    
    async def get_ids_by_category_sorted_by_date(self, category: str) -> List[PydanticObjectId]:
        """Получить список id продуктов в категории, отсортированных по дате создания (ObjectId)."""
        cursor = self.get_collection().find(
            {"category": category},
            projection={"_id": 1}
        ).sort("_id", 1)
        return [PydanticObjectId(doc["_id"]) async for doc in cursor]

    async def get_by_category_and_index(self, category: str, idx: int) -> Product:
        ids = await self.get_ids_by_category_sorted_by_date(category)
        return await self.find_one_by_id(ids[idx])
    
    async def count_in_category(self, category) -> int:
        return await self.get_collection().count_documents({"category": category})

class ProductAdditional(BaseModel):
    id: Optional[PydanticObjectId] = None
    name: LocalizedString
    category: str

    short_description: LocalizedString

    price: LocalizedMoney
    disallowed_products: list[PydanticObjectId] = []

class AdditionalsRepository(AppAbstractRepository[ProductAdditional]):
    class Meta:
        collection_name = 'additionals'

    async def get(self, product: Product):
        """Возвращает все additionals в категории, которые разрешены для данного продукта."""
        return await self.find_by({"category": product.category, "disallowed_products": {"$nin": [str(product.id)]}})
    
    def get_by_name(self, name, allowed_additionals, lang):
        return next((a for a in allowed_additionals if a.name.get(lang) == name), None)

class Promocode(BaseModel):
    id: Optional[PydanticObjectId] = None
    code: str
    action: PromocodeAction
    
    description: LocalizedString
    only_newbies: bool

    already_used: int = 0
    max_usages: int = -1

    expire_date: Optional[datetime.datetime] = None
    
    
    async def check_promocode(self, customer_orders_amount: int) -> PromocodeCheckResult:
        if self.expire_date and self.expire_date < datetime.datetime():
            return PromocodeCheckResult.expired
        elif self.only_newbies and customer_orders_amount > 0:
            return PromocodeCheckResult.only_newbies
        elif self.max_usages != -1 and self.max_usages <= self.already_used:
            return PromocodeCheckResult.max_usages_reached
        
        return PromocodeCheckResult.ok

class PromocodesRepository(AppAbstractRepository[Promocode]):
    class Meta:
        collection_name = 'promocodes'

class Inviter(BaseModel):
    id: Optional[PydanticObjectId] = None
    inviter_code: str

    name: str

class InvitersRepository(AppAbstractRepository[Inviter]):
    class Meta:
        collection_name = 'inviters'

class DeliveryService(BaseModel):
    id: Optional[PydanticObjectId] = None
    name: LocalizedString  # Название сервиса
    is_foreign: bool = False
    
    price: LocalizedMoney = LocalizedMoney.from_dict(
                                           {
                                            "RUB": 500.0,
                                            "USD": 7.0
                                           }
                                           )
    requirements_options: list[DeliveryRequirementsList] # для почты россии, например, можно оформить как по адресу с ФИО, так и просто по номеру до востребования
    selected_option: Optional[DeliveryRequirementsList] = None # для заполнения в будущем при конфигурации

class DeliveryServicesRepository(AppAbstractRepository[DeliveryService]):
    class Meta:
        collection_name = 'delivery_services'
    
    async def get_all(self, is_foreign: bool) -> Iterable[DeliveryService]:
        return await self.find_by({"is_foreign": is_foreign})

class Customer(BaseModel):
    id: Optional[PydanticObjectId] = None
    user_id: int
    role: str = "default"

    invited_by: str
    kicked: bool = False

    lang: str
    
    currency: str
    bonus_wallet: Money
    delivery_info: DeliveryInfo = Field(default_factory=DeliveryInfo)
    
    def get_currency_symbol(self, iso_code: str) -> str:
        return SUPPORTED_CURRENCIES.get(iso_code, iso_code)

    def get_selected_currency_symbol(self) -> str:
        return self.get_currency_symbol(self.currency)

    async def change_selected_currency(self, iso: str, acc: AsyncCurrencyConverter):
        """Изменить основную валюту"""
        if iso not in SUPPORTED_CURRENCIES:
            raise ValueError(f"Unsupported currency: {iso}")

        bon_wal = self.bonus_wallet
        if bon_wal.amount > 0:
            try:
                amount = await acc.convert(bon_wal.amount, self.currency, iso)
            except Exception as e:
                # Логируем ошибку и не меняем валюту
                logging.getLogger(__name__).critical(f"Ошибка конвертации валюты: {e}")
                raise RuntimeError(
                    "Сервис конвертации валют временно недоступен. Попробуйте позже."
                ) from e
            self.bonus_wallet = Money(iso, amount)

        self.currency = iso

    async def get_cart(self, db: "DatabaseService") -> Iterable[CartEntry]:
        return await db.get_by_query(CartEntry, {"customer_id": self.id})

    async def get_orders(self, db: "DatabaseService") -> Iterable[Order]:
        return await db.get_by_query(Order, {"customer_id": self.id})

    async def add_to_cart(self, db: "DatabaseService", product: Product,
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

class CustomersRepository(AppAbstractRepository[Customer]):
    class Meta:
        collection_name = 'customers'

    def __init__(self, database: "DatabaseService"):
        super().__init__(database)
        self.logger = logging.getLogger(__name__)

    async def new_customer(self, user_id, inviter: Inviter = None, lang: str = "?", currency: str = "RUB") -> Customer:
        customer = Customer(
                user_id=user_id,
                invited_by=inviter.inviter_code if inviter else "",
                lang=lang,
                currency=currency,
                bonus_wallet=Money(currency, 0.0)
            )
        
        await self.save(customer)
        return customer

    async def get_customer_by_id(self, user_id: int) -> Optional[Customer]:
        """Возвращает пользователя по его user_id. Если пользователь не найден, возвращает None."""
        try:
            doc = await self.find_one_by({"user_id": user_id})

            return doc or None
        except PyMongoError as e:
            handle_error(self.logger, e)

class Category(BaseModel):
    id: Optional[PydanticObjectId] = None
    name: str
    localized_name: LocalizedString

class CategoriesRepository(AppAbstractRepository[Category]):
    class Meta:
        collection_name = 'categories'

    def __init__(self, database: "DatabaseService"):
        super().__init__(database)
        self.logger = logging.getLogger(__name__)

    async def get_all(self) -> Optional[Iterable[Category]]:
        try:
            doc = await self.find_by({})
            return doc or None
        except PyMongoError as e:
            handle_error(self.logger, e)

def handle_error(logger, error: PyMongoError):
    logger.error(f"Database error: {error}") 