import datetime
import logging
from typing import Optional, List, Iterable, TYPE_CHECKING

from pydantic import BaseModel, Field
from pydantic_mongo import AsyncAbstractRepository, PydanticObjectId
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from src.classes.config import CURRENCY_CHANGE_COOLDOWN_DAYS, SUPPORTED_CURRENCIES

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
        """Возвращает список включённых переключателей из списка switches."""
        return [switch for switch in self.switches if switch.enabled]

    @staticmethod
    def calculate_price(switches: list[ConfigurationSwitch], currency):
        """Возвращает сумму цен всех переданных переключателей."""
        return sum(switch.price.data[currency] for switch in switches)

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
    price: LocalizedPrice = Field(default_factory=lambda: LocalizedPrice(data={"RUB": 0, "USD": 0}))

class ConfigurationOption(BaseModel):
    name: LocalizedString
    text: LocalizedString
    photo_id: Optional[str] = None
    video_id: Optional[str] = None
    chosen: int

    choices: List[ConfigurationChoice | ConfigurationSwitches]
    
    def get_chosen(self):
        return self.choices[self.chosen - 1]
    
    def set_chosen(self, choice: ConfigurationChoice):
        self.chosen = self.choices.index(choice)+1
    
    def get_index_by_label(self, label: str, lang: str) -> int:
        for i, choice in enumerate(self.choices):
            if hasattr(choice, "label") and choice.label.data[lang] == label:
                return i
        raise ValueError(f"Choice with label '{label}' not found in option '{self.name.data[lang]}'")
    
    def get_by_label(self, label: str, lang: str) -> ConfigurationChoice | ConfigurationSwitches:
        for choice in self.choices:
            if hasattr(choice, "label") and choice.label.data[lang] == label:
                return choice
        raise ValueError(f"Choice with label '{label}' not found in option '{self.name.data[lang]}'")
    

class ProductConfiguration(BaseModel):
    options: list[ConfigurationOption]
    additionals: list["ProductAdditional"] = []
    
    
    def get_all_options_localized_names(self, lang):
        return [option.name.data[lang] for option in self.options]
    
    def get_option_by_name(self, name, lang):
        return next((idx, option) for idx, option in enumerate(self.options)
                    if option.name.data[lang] == name)
        


class Product(BaseModel):
    id: Optional[PydanticObjectId] = None
    order_no: int = None
    name: LocalizedString
    category: str

    short_description: LocalizedString
    short_description_photo_id: str

    long_description: LocalizedString
    long_description_photo_id: Optional[str] = None
    long_description_video_id: Optional[str] = None

    base_price: LocalizedPrice

    configuration_photo_id: Optional[str] = None
    configuration_video_id: Optional[str] = None
    configuration: ProductConfiguration

class ProductsRepository(AsyncAbstractRepository[Product]):
    class Meta:
        collection_name = 'products'

    async def insert(self, model: Product, category, db: "DB"):
        """Добавляет продукт в базу с присвоением номера заказа."""
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
        """Возвращает все additionals в категории, которые разрешены для данного продукта."""
        return await self.find_by({"category": category, "disallowed_products": {"$nin": [str(product_id)]}})
    
    def get_by_name(self, name, allowed_additionals, lang):
        return next(a for a in allowed_additionals if a.name.data[lang] == name)




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

class CustomerBonusWallet(BaseModel):
    bonus_balance: dict[str, float] = Field(default_factory=lambda: {cur: 0.0 for cur in SUPPORTED_CURRENCIES.keys()})

    def add_bonus_funds(self, amount: float, currency: str):
        """Пополнить бонусный баланс для указанной валюты"""
        if currency not in self.bonus_balance:
            self.bonus_balance[currency] = 0.0
        self.bonus_balance[currency] += amount

    def get_bonus_balance(self, currency: str) -> float:
        """Получить бонусный баланс для указанной валюты"""
        return self.bonus_balance.get(currency, 0.0)


class DeliveryRequirement(BaseModel):
    name: LocalizedString
    description: LocalizedString
    value: Optional[str] = None # для заполнения в будущем при конфигурации

class DeliveryRequirementsList(BaseModel):
    name: LocalizedString # типо "По номеру", или "По адресу и ФИО"
    description: LocalizedString
    requirements: list[DeliveryRequirement]

class DeliveryService(BaseModel):
    id: Optional[PydanticObjectId] = None
    name: LocalizedString  # Название сервиса
    is_foreign: bool = False
    
    price: LocalizedPrice = LocalizedPrice(data=
                                           {
                                            "RUB": 500.0,
                                            "USD": 7.0
                                           }
                                           )
    requirements_options: list[DeliveryRequirementsList] # для почты россии, например, можно оформить как по адресу с ФИО, так и просто по номеру до востребования
    selected_option: Optional[DeliveryRequirementsList] = None # для заполнения в будущем при конфигурации

class DeliveryServicesRepository(AsyncAbstractRepository[DeliveryService]):
    class Meta:
        collection_name = 'delivery_services'

class DeliveryInfo(BaseModel):
    is_foreign: bool = False  # Вне РФ?
    service: Optional[DeliveryService] = None

class Customer(BaseModel):
    id: Optional[PydanticObjectId] = None
    user_id: int
    role: str = "default"

    invited_by: str
    kicked: bool = False

    lang: str
    
    currency: str
    bonus_wallet: CustomerBonusWallet = CustomerBonusWallet()
    delivery_info: DeliveryInfo = Field(default_factory=DeliveryInfo)

    
    def get_currency_symbol(self, iso_code: str) -> str:
        return SUPPORTED_CURRENCIES.get(iso_code, iso_code)

    def get_selected_currency_symbol(self) -> str:
        return self.get_currency_symbol(self.currency)

    def change_selected_currency(self, iso: str):
        """Изменить основную валюту"""
        if iso not in SUPPORTED_CURRENCIES:
            raise ValueError(f"Unsupported currency: {iso}")

        self.currency = iso

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


class CategoriesRepository(AsyncAbstractRepository[Category]):
    class Meta:
        collection_name = 'categories'

    def __init__(self, database: AsyncDatabase):
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