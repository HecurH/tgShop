import base64
import datetime
import logging
from typing import Any, Dict, TypeVar, Optional, List, Iterable, TYPE_CHECKING

from pydantic import BaseModel, Field
from pydantic_mongo import AsyncAbstractRepository, PydanticObjectId
from pymongo.errors import PyMongoError

from core.helper_classes import Cryptography
from configs.supported import SUPPORTED_CURRENCIES

if TYPE_CHECKING:
    from core.db import DatabaseService

T = TypeVar("T")

class AppAbstractRepository(AsyncAbstractRepository[T]):
    def __init__(self, dbs: "DatabaseService"):
        super().__init__(dbs.db)
        self.dbs = dbs
    
class LocalizedString(BaseModel):
    data: dict[str, str]

class LocalizedPrice(BaseModel):
    data: dict[str, float] = {}
    
    def to_text(self, currency: str) -> str:
        return f"{self.data[currency]:.2f}{SUPPORTED_CURRENCIES.get(currency, currency)}"
    
    def __add__(self, other):
        if not isinstance(other, LocalizedPrice):
            return NotImplemented
        # Складываем значения по ключам, если ключа нет — считаем 0
        result = {cur: self.data.get(cur, 0) + other.data.get(cur, 0)
                  for cur in set(self.data) | set(other.data)}
        return LocalizedPrice(data=result)

    def __iadd__(self, other):
        if not isinstance(other, LocalizedPrice):
            return NotImplemented
        for cur in set(self.data) | set(other.data):
            self.data[cur] = self.data.get(cur, 0) + other.data.get(cur, 0)
        return self
    
    def __radd__(self, other):
        if other == 0:
            return LocalizedPrice(data=self.data.copy())
        return self.__add__(other)
    
    
    def __mul__(self, other):
        if isinstance(other, (int, float)):
            return LocalizedPrice(data={cur: val * other for cur, val in self.data.items()})
        if isinstance(other, LocalizedPrice):
            # Поэлементное умножение по ключам
            result = {cur: self.data.get(cur, 0) * other.data.get(cur, 0)
                      for cur in set(self.data) | set(other.data)}
            return LocalizedPrice(data=result)
        return NotImplemented

    def __rmul__(self, other):
        return self.__mul__(other)

    def __imul__(self, other):
        if isinstance(other, (int, float)):
            for cur in self.data:
                self.data[cur] *= other
            return self
        if isinstance(other, LocalizedPrice):
            for cur in set(self.data) | set(other.data):
                self.data[cur] = self.data.get(cur, 0) * other.data.get(cur, 0)
            return self
        return NotImplemented

class SecureValue(BaseModel):
    iv: str = ""
    ciphertext: str = ""
    tag: str = ""

    def get(self) -> Optional[str]:
        """Дешифрует и возвращает строковое значение."""
        if not self.iv or not self.ciphertext or not self.tag:
            return None
        return Cryptography.decrypt_data(
            base64.b64decode(self.iv),
            base64.b64decode(self.ciphertext),
            base64.b64decode(self.tag)
        )

    def update(self, text: str):
        """Шифрует строку и сохраняет результат в поля."""
        iv, ciphertext, tag = Cryptography.encrypt_data(text)
        self.iv = base64.b64encode(iv).decode()
        self.ciphertext = base64.b64encode(ciphertext).decode()
        self.tag = base64.b64encode(tag).decode()

class Order(BaseModel):
    id: Optional[PydanticObjectId] = None
    customer_id: PydanticObjectId
    promocodes: list[PydanticObjectId]

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
        return await self.get_collection().count_documents({"customer_id": str(customer.id), "order_id": None})
    
    async def get_customer_cart_ids_by_customer_sorted_by_date(self, customer: "Customer") -> List[PydanticObjectId]:
        """Получить список id продуктов в категории, отсортированных по дате создания (ObjectId)."""
        cursor = self.get_collection().find(
            {"customer_id": str(customer.id),
             "order_id": None},
            projection={"_id": 1}
        ).sort("_id", 1)
        return [PydanticObjectId(doc["_id"]) async for doc in cursor]

    async def get_customer_cart_entry_by_id(self, customer: "Customer", idx: int) -> CartEntry:
        ids = await self.get_customer_cart_ids_by_customer_sorted_by_date(customer)
        return await self.find_one_by_id(ids[idx])
    
    async def calculate_customer_cart_price(self, customer: "Customer"):
        # sourcery skip: comprehension-to-generator
        entries: Iterable[CartEntry] = await self.find_by({"customer_id": str(customer.id), "order_id": None})
        return sum(
            [
                (((await self.dbs.products.find_one_by_id(entry.product_id)).base_price + entry.configuration.price) * entry.quantity)
                for entry in entries
            ],
            LocalizedPrice()
        )
        
class ConfigurationSwitch(BaseModel):
    name: LocalizedString
    price: LocalizedPrice = Field(default_factory=lambda: LocalizedPrice(data={"ru": 0, "en": 0}))

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
        return sum((switch.price for switch in switches), LocalizedPrice())

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
            if switch.name.data[lang] == name:
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
    price: LocalizedPrice = Field(default_factory=lambda: LocalizedPrice(data={"RUB": 0, "USD": 0}))

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
            enabled_names = [sw.name.data["en"] for sw in chosen.get_enabled()]
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
            if hasattr(choice, "label") and choice.label.data[lang] == label:
                return key
    
    def get_by_label(self, label: str, lang: str) -> Optional[ConfigurationChoice | ConfigurationSwitches]:
        for choice in self.choices.values():
            if hasattr(choice, "label") and choice.label.data[lang] == label:
                return choice

    def calculate_price(self):
        conf_choice = self.get_chosen().model_copy(deep=True)
        price = conf_choice.price.model_copy(deep=True) if isinstance(conf_choice, ConfigurationChoice) else LocalizedPrice()
        price += sum((choice.calculate_price(choice.get_enabled()) for choice in self.choices.values() if isinstance(choice, ConfigurationSwitches)), LocalizedPrice())
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
    price: LocalizedPrice = None

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
        return [option.name.data[lang] for option in self.options.values()]
    
    def get_option_by_name(self, name, lang):
        return next((key, option) for key, option in self.options.items()
                    if option.name.data[lang] == name)
        
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
        return sum((additional.price.model_copy(deep=True) for additional in self.additionals), LocalizedPrice())
    
    def calculate_options_price(self):
        return sum((option.calculate_price() for option in self.options.values()), LocalizedPrice())
    
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

    base_price: LocalizedPrice

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

    price: LocalizedPrice
    disallowed_products: list[PydanticObjectId] = []

class AdditionalsRepository(AppAbstractRepository[ProductAdditional]):
    class Meta:
        collection_name = 'additionals'

    async def get(self, product: Product):
        """Возвращает все additionals в категории, которые разрешены для данного продукта."""
        return await self.find_by({"category": product.category, "disallowed_products": {"$nin": [str(product.id)]}})
    
    def get_by_name(self, name, allowed_additionals, lang):
        return next((a for a in allowed_additionals if a.name.data[lang] == name), None)

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
    value: SecureValue = SecureValue() # для заполнения в будущем при конфигурации

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

    async def get_cart(self, db: "DatabaseService") -> Iterable[CartEntry]:
        return await db.get_by_query(CartEntry, {"customer_id": str(self.id)})

    async def get_orders(self, db: "DatabaseService") -> Iterable[Order]:
        return await db.get_by_query(Order, {"customer_id": str(self.id)})

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