import datetime
import logging
from typing import Any, Dict, TypeVar, Optional, List, Iterable, TYPE_CHECKING

from pydantic import BaseModel, Field
from pydantic_mongo import AsyncAbstractRepository, PydanticObjectId
from pymongo.errors import PyMongoError

from configs.supported import SUPPORTED_CURRENCIES
from core.helper_classes import AsyncCurrencyConverter
from schemas.types import LocalizedMoney, LocalizedString, Money, SecureValue

if TYPE_CHECKING:
    from core.db import DatabaseService

T = TypeVar("T")

class AppAbstractRepository(AsyncAbstractRepository[T]):
    def __init__(self, dbs: "DatabaseService"):
        super().__init__(dbs.db)
        self.dbs = dbs
    
class Order(BaseModel):
    id: Optional[PydanticObjectId] = None
    customer_id: PydanticObjectId
    promocodes: list[PydanticObjectId]
    
    total_price: Money

    async def add_promocode(self, promocode: "Promocode", db: "DatabaseService") -> Optional[bool]:
        user: "Customer" = await db.get_by_id(Customer, self.customer_id)
        if promocode.only_newbies:
            count = await db.get_count_by_query(Order, {"customer_id": self.customer_id})
            if count != 0:
                return False

class OrdersRepository(AppAbstractRepository[Order]):
    class Meta:
        collection_name = 'orders'

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
    
    async def calculate_customer_cart_price(self, customer: "Customer"):
        # sourcery skip: comprehension-to-generator
        entries: Iterable[CartEntry] = await self.find_by({"customer_id": customer.id, "order_id": None})
        return sum(
            [
                (((await self.dbs.products.find_one_by_id(entry.product_id)).base_price + entry.configuration.price) * entry.quantity)
                for entry in entries
            ],
            LocalizedMoney()
        )
        
class ConfigurationSwitch(BaseModel):
    name: LocalizedString
    price: LocalizedMoney = Field(default_factory=lambda: LocalizedMoney.from_dict({"ru": 0, "en": 0}))

    enabled: bool = False
    
    def update(self, base_sw: "ConfigurationSwitch"):
        self.name=base_sw.name
        self.price=base_sw.price

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
    def calculate_price(switches: list[ConfigurationSwitch]):
        """Возвращает сумму цен всех переданных переключателей."""
        return sum((switch.price for switch in switches), LocalizedMoney())

    def update(self, base_choice: "ConfigurationSwitches"):
        self.label=base_choice.label
        self.description=base_choice.description
        self.photo_id=base_choice.photo_id
        self.video_id=base_choice.video_id
        
        for i, switch in enumerate(base_choice.switches):
            if len(self.switches)-1 < i:
                self.switches.append(switch)
                continue
            self.switches[i].update(switch)
    
    def toggle_by_localized_name(self, name, lang):
        for switch in self.switches:
            if switch.name.get(lang) == name:
                switch.enabled = not switch.enabled
                break 

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
    
    can_be_blocked_by: List[str] = [] # формат типо 'option/choice'
    blocks_price_determination: bool = Field(default=False)
    price: LocalizedMoney = Field(default_factory=lambda: LocalizedMoney.from_dict({"RUB": 0, "USD": 0}))

    def update(self, base_choice: "ConfigurationChoice"):
        self.label=base_choice.label
        self.description=base_choice.description
        self.photo_id=base_choice.photo_id
        self.video_id=base_choice.video_id
        self.existing_presets=base_choice.existing_presets
        self.existing_presets_quantity=base_choice.existing_presets_quantity
        self.is_custom_input=base_choice.is_custom_input
        self.blocks_price_determination=base_choice.blocks_price_determination
        self.price=base_choice.price
    
    def check_blocked_all(self, options: Dict[str, Any]) -> bool:
        return any(
            self.check_blocked_path(path, options)
            for path in self.can_be_blocked_by
        )
        
    def get_blocking_path(self, options: Dict[str, Any]) -> Optional[str]:
        return next(
            (
                path
                for path in self.can_be_blocked_by
                if self.check_blocked_path(path, options)
            ),
            None
        )
    
    def check_blocked_path(self, path, options: Dict[str, Any]) -> bool:
        *opt_keys, last_key = path.split("/")
        
        option = options.get(opt_keys[0]) if opt_keys else None
        
        chosen = option.get_chosen()
        if option.choices.get(last_key) == chosen and len(opt_keys) == 1:
            return True
        if isinstance(chosen, ConfigurationSwitches) and len(opt_keys) > 1:
            enabled_names = [sw.name.get("en") for sw in chosen.get_enabled()]
            if opt_keys[1] in enabled_names:
                return True
        return False

class ConfigurationOption(BaseModel):
    name: LocalizedString
    text: LocalizedString
    photo_id: Optional[str] = None
    video_id: Optional[str] = None
    chosen: str

    choices: Dict[str, ConfigurationChoice | ConfigurationSwitches]
    
    def get_chosen(self):
        return self.choices.get(self.chosen)
    
    def set_chosen(self, choice: ConfigurationChoice):
        self.chosen = next((key for key, value in self.choices.items() if value == choice), None)
    
    def get_key_by_label(self, label: str, lang: str) -> Optional[str]:
        for key, choice in self.choices.items():
            if hasattr(choice, "label") and choice.label.get(lang) == label:
                return key
    
    def get_by_label(self, label: str, lang: str) -> Optional[ConfigurationChoice | ConfigurationSwitches]:
        for choice in self.choices.values():
            if hasattr(choice, "label") and choice.label.get(lang) == label:
                return choice

    def calculate_price(self):
        conf_choice = self.get_chosen().model_copy(deep=True)
        price = conf_choice.price.model_copy(deep=True) if isinstance(conf_choice, ConfigurationChoice) else LocalizedMoney()
        price += sum((choice.calculate_price(choice.get_enabled()) for choice in self.choices.values() if isinstance(choice, ConfigurationSwitches)), LocalizedMoney())
        return price
    
    def get_switches(self):
        switch_list = []
        for choice in self.choices.values():
            if isinstance(choice, ConfigurationSwitches):
                switch_list.extend(choice.get_enabled())
        return switch_list
                

    def update(self, option: "ConfigurationOption"):
        self.name = option.name
        self.text = option.text
        self.photo_id = option.photo_id
        self.video_id = option.video_id
        
        # Обновляем choices
        for choice_key, base_choice in option.choices.items():
            if choice_key not in option.choices:
                self.choices[choice_key] = base_choice
                continue
            
            self.choices[choice_key].update(base_choice)
        # Удаляем choices, которых больше нет в base
        for choice_key in list(option.choices.keys()):
            if choice_key not in option.choices:
                del option.choices[choice_key]

class ProductConfiguration(BaseModel):
    options: Dict[str, ConfigurationOption]
    additionals: list["ProductAdditional"] = []
    price: LocalizedMoney = None

    def __init__(self, **data):
        super().__init__(**data)
        if not self.price: self.update_price()
    
    
    def update(self, base_configuration: "ProductConfiguration", allowed_additionals: List["ProductAdditional"]):
        """
        Обновляет текущую конфигурацию на основе base_configuration,
        сохраняя пользовательские выборы.
        """
        # Обновляем опции
        for key, base_option in base_configuration.options.items():
            if key not in self.options:
                # Если опция новая, просто добавляем
                self.options[key] = base_option
                continue

            self.options[key].update(base_option)

        # Удаляем опции, которых больше нет в base
        for key in list(self.options.keys()):
            if key not in base_configuration.options:
                del self.options[key]

        base_additional_ids = {add.id for add in allowed_additionals}
        self.additionals = [add for add in self.additionals if add.id in base_additional_ids]

    def get_all_options_localized_names(self, lang):
        return [option.name.get(lang) for option in self.options.values()]
    
    def get_option_by_name(self, name, lang):
        return next((key, option) for key, option in self.options.items()
                    if option.name.get(lang) == name)
        
    def get_additionals_ids(self) -> Iterable[PydanticObjectId]:
        return [add.id for add in self.additionals]
    
    def get_localized_names_by_path(self, path, lang) -> List[str]:
        *opt_keys, last_key = path.split("/")
        result = []
        # Получаем опцию
        option = self.options.get(opt_keys[0]) if opt_keys else None
        if not option:
            return result
        # Добавляем имя опции
        result.append(option.name.data.get(lang))
        # Получаем выбор
        choice = option.choices.get(opt_keys[1]) if len(opt_keys) > 1 else option.choices.get(last_key)
        if not choice:
            return result
        # Добавляем имя выбора
        if hasattr(choice, "label"):
            result.append(choice.label.data.get(lang))
        # Если есть переключатель (switch)
        if len(opt_keys) > 2 and hasattr(choice, "switches"):
            if switch := next(
                (
                    sw
                    for sw in choice.switches
                    if sw.name.data.get(
                        "ru", next(iter(sw.name.data.values()), "")
                    )
                    == last_key
                ),
                None,
            ):
                result.append(switch.name.data.get(lang))
        return result
        
    def calculate_additionals_price(self):
        return sum((additional.price.model_copy(deep=True) for additional in self.additionals), LocalizedMoney())
    
    def calculate_options_price(self):
        return sum((option.calculate_price() for option in self.options.values()), LocalizedMoney())
    
    def update_price(self):
        self.price = self.calculate_additionals_price() + self.calculate_options_price()
        
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
    only_newbies: bool
    product_restriction: list[PydanticObjectId]

    already_used: int = 0
    max_usages: int = -1

    expire_date: datetime.datetime

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

class DeliveryRequirement(BaseModel):
    name: LocalizedString
    description: LocalizedString
    value: SecureValue = SecureValue() # для заполнения в будущем при конфигурации

class DeliveryRequirementsList(BaseModel):
    name: LocalizedString # типо "По номеру", или "По адресу и ФИО"
    description: LocalizedString
    requirements: list[DeliveryRequirement]

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