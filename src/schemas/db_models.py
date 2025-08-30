import asyncio
import datetime
import logging
from typing import Any, Dict, Generic, Type, TypeVar, Optional, List, Iterable, TYPE_CHECKING

from pydantic import BaseModel, Field
from pydantic_mongo import AsyncAbstractRepository, PydanticObjectId
from pymongo.results import InsertOneResult

from configs.payments import SUPPORTED_PAYMENT_METHODS
from configs.supported import SUPPORTED_CURRENCIES
from core.helper_classes import AsyncCurrencyConverter, Context
from schemas.enums import OrderStateKey, PromocodeCheckResult
from schemas.payment_models import PaymentMethod
from schemas.types import LocalizedMoney, LocalizedString, Money, OrderState, Discount, SecureValue

if TYPE_CHECKING:
    from core.db import DatabaseService

T = TypeVar("T")
TModel = TypeVar("TModel", bound="AppBaseModel[Any]")


class AppAbstractRepository(AsyncAbstractRepository[T]):
    def __init__(self, dbs: "DatabaseService"):
        super().__init__(dbs.db)
        self.dbs = dbs
        
# класс BaseModel, но со своей функцией для загрузки сериализованных объектов
class AppBaseModel(BaseModel, Generic[TModel]):
    @classmethod
    async def from_fsm_context(cls: Type[TModel], ctx: Context, key: str, default: Optional[TModel] = None) -> Optional[TModel]:
        """Загрузка напрямую из контекста по ключу"""
        value: Optional[dict] = await ctx.fsm.get_value(key)
        return cls(**value) if value else default
    
    @classmethod
    async def load_many_from_fsm(cls: Type[TModel], ctx: Context, keys: List[str]) -> tuple[Optional[TModel]]:
        """Загрузка нескольких моделей из FSM по списку ключей"""
        tasks = [cls.from_fsm_context(ctx, key) for key in keys]
        return tuple(await asyncio.gather(*tasks))
    
    async def save_in_fsm(self, ctx: Context, key: str):
        """Сохранение в контекст по ключу"""
        await ctx.fsm.update_data({key: self.model_dump()})
    
    
class OrderPriceDetails(AppBaseModel):
    products_price: Money  # сумма товаров без скидок и доставки
    promocode_discount: Optional[Money] = None  # скидка по промокоду
    
    delivery_price: Money  # доставка
    bonuses_applied: Optional[Money] = None # сколько бонусных средств для оплаты
    
    total_price: Optional[Money] = None  # сколько надо заплатить настоящими деньгами
    
    customer_paid: bool = False
    payment_time: Optional[datetime.datetime] = None

    def recalculate_price(self):
        products_price_after_promocode = (self.products_price - self.promocode_discount) if self.promocode_discount else self.products_price
        total = products_price_after_promocode + self.delivery_price
        
        self.total_price = total - self.bonuses_applied if self.bonuses_applied else total
    
class Order(AppBaseModel):
    id: Optional[PydanticObjectId] = None
    puid: Optional[str] = None
    number: Optional[int] = None
    
    customer_id: PydanticObjectId
    state: OrderState = OrderState(key=OrderStateKey.forming)
    delivery_info: Optional["DeliveryInfo"] = None # при запросе удаления перс данных, обычно не должен быть пуст

    promocode: Optional[PydanticObjectId] = None

    price_details: OrderPriceDetails
    payment_method_key: Optional[str] = None # key for SUPPORTED_PAYMENT_METHODS
    
    @property
    def payment_method(self) -> Optional[PaymentMethod]:
        return SUPPORTED_PAYMENT_METHODS.get_by_key(self.payment_method_key)
    
    @staticmethod
    def generate_puid(hex_string: str, length: int = 5) -> str:
        ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
        BASE = len(ALPHABET)
        
        try:
            num = int(hex_string, 16)
        except ValueError as e:
            raise ValueError("Input must be a valid hex string") from e
        
        max_value = BASE ** length
        num %= max_value
        
        result = []
        for _ in range(length):
            num, remainder = divmod(num, BASE)
            result.append(ALPHABET[remainder])
        
        return ''.join(reversed(result))

    def __init__(self, **data):
        super().__init__(**data)
        if not self.puid and self.id:
            self.puid = self.generate_puid(str(self.id))

    async def set_promocode(self, promocode: Optional["Promocode"]):
        self.price_details.promocode_discount = promocode.action.get_discount(self.price_details.products_price) if promocode else None
        self.price_details.recalculate_price()
    
    async def update_applied_bonuses(self, customer_bonus_balance: Optional[Money]):
        if not customer_bonus_balance:
            self.price_details.bonuses_applied = None
            return
        
        price_details = self.price_details
        products_price_after_promocode = (price_details.products_price - price_details.promocode_discount) if price_details.promocode_discount else price_details.products_price
        total = products_price_after_promocode + price_details.delivery_price
        
        self.price_details.bonuses_applied = min(total, customer_bonus_balance)

class OrdersRepository(AppAbstractRepository[Order]):
    class Meta:
        collection_name = 'orders'
        
    def new_order(self, customer: "Customer", products_price: LocalizedMoney) -> Order:
        delivery_info = customer.delivery_info
        currency = customer.currency
        
        price_details = OrderPriceDetails(products_price=products_price.get_money(currency),
                                          delivery_price=delivery_info.service.price.get_money(currency)
                                          )
        price_details.recalculate_price()
        
        return Order(customer_id=customer.id, delivery_info=delivery_info, price_details=price_details)
    
    async def get_customer_orders(self, customer: "Customer") -> Iterable[Order]:
        return await self.find_by({"customer_id": customer.id})

    async def count_customer_orders(self, customer: "Customer") -> int:
        return await self.get_collection().count_documents({"customer_id": customer.id})
    
    async def save(self, order: Order):
        order.number = order.number or await self.dbs.get_next_for_counter(self.Meta.collection_name)
        
        # puid только для нового заказа
        if not order.id:
            result = await super().save(order)
            inserted_id = str(result.inserted_id)
            
            order.id = PydanticObjectId(inserted_id)
            order.puid = Order.generate_puid(inserted_id)
            
        await super().save(order)

class CartEntry(AppBaseModel):
    id: Optional[PydanticObjectId] = None
    customer_id: PydanticObjectId
    product_id: PydanticObjectId
    frozen_product: Optional["Product"] = None # только для сформированных заказов
    
    order_id: Optional[PydanticObjectId] = None

    quantity: int = Field(default=1, gt=0)

    configuration: "ProductConfiguration"
    
    @property
    def need_to_confirm_price(self) -> bool:
        return self.configuration.requires_price_confirmation

class CartEntriesRepository(AppAbstractRepository[CartEntry]):
    class Meta:
        collection_name = 'cart_entries'
    
    async def add_to_cart(self, product: "Product", customer: "Customer"):
        await self.save(CartEntry(customer_id=customer.id, 
                      product_id=product.id, 
                      configuration=product.configuration))
        
    async def count_customer_cart_entries(self, customer: "Customer"):
        return await self.get_collection().count_documents({"customer_id": customer.id, "order_id": None})
    
    async def get_customer_cart_ids_sorted_by_date(self, customer: "Customer") -> List[PydanticObjectId]:
        """Получить список id продуктов в категории, отсортированных по дате создания (ObjectId)."""
        cursor = self.get_collection().find(
            {"customer_id": customer.id,
             "order_id": None},
            projection={"_id": 1}
        ).sort("_id", 1)
        return [PydanticObjectId(doc["_id"]) async for doc in cursor]

    async def get_customer_cart_entries(self, customer: "Customer") -> Iterable[CartEntry]:
        return await self.find_by({"customer_id": customer.id, "order_id": None}, sort=[("_id", 1)])
    
    async def get_entries_by_order(self, order: "Order", query: Optional[dict] = None) -> Iterable[CartEntry]:
        base_query = {**(query or {}), "order_id": order.id}
        return await self.find_by(base_query, sort=[("_id", 1)])

    async def get_customer_cart_entry_by_id(self, customer: "Customer", idx: int) -> Optional[CartEntry]:
        ids = await self.get_customer_cart_ids_sorted_by_date(customer)
        if not ids: return None
        
        return await self.find_one_by_id(ids[idx]) if 0 <= idx < len(ids) else None
    
    async def assign_cart_entries_to_order(self, customer: "Customer", order: "Order"):
        entries = await self.get_customer_cart_entries(customer)
        
        if not entries:
            return
        
        product_ids = [entry.product_id for entry in entries]
        products = await self.dbs.products.find_by({"_id": {"$in": product_ids}})
        
        products_map = {product.id: product for product in products}
        
        for entry in entries:
            entry.order_id = order.id
            entry.frozen_product = products_map.get(entry.product_id)
            
        await self.save_many(entries)
    
    async def calculate_customer_cart_price(self, customer: "Customer") -> LocalizedMoney:
        entries: Iterable[CartEntry] = await self.find_by({"customer_id": customer.id, "order_id": None})
        products: Iterable[Product] = await self.dbs.products.find_by({"_id": {"$in": [entry.product_id for entry in entries]}})
        product_map: Dict[PydanticObjectId, Product] = {
            product.id: product for product in products
        }

        total_price = LocalizedMoney()
        for entry in entries:
            if product := product_map.get(entry.product_id):
                entry_total = (product.price + entry.configuration.price) * entry.quantity
                total_price += entry_total
        return total_price
    
    async def check_price_confirmation_in_cart(self, customer: "Customer") -> bool:
        query = {
            "customer_id": customer.id,
            "order_id": None,
            "configuration.requires_price_confirmation": True
        }

        document = await self.get_collection().find_one(query, projection={"_id": 1})
        return document is not None

class ConfigurationSwitch(AppBaseModel):
    name: LocalizedString
    price: LocalizedMoney = Field(default_factory=lambda: LocalizedMoney.from_dict({"ru": 0, "en": 0}))

    enabled: bool = False
    
    def update(self, base_sw: "ConfigurationSwitch"):
        self.name=base_sw.name
        self.price=base_sw.price

class ConfigurationSwitches(AppBaseModel):
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

    def update(self, update_from_switches: "ConfigurationSwitches"):
        self.label = update_from_switches.label
        self.description = update_from_switches.description
        self.photo_id = update_from_switches.photo_id
        self.video_id = update_from_switches.video_id
        
        for i, switch in enumerate(update_from_switches.switches):
            if len(self.switches) <= i:
                self.switches.append(switch)
                continue
            self.switches[i].update(switch)
    
    def toggle_by_localized_name(self, name, lang):
        for switch in self.switches:
            if switch.name.get(lang) == name:
                switch.enabled = not switch.enabled
                break 

class ConfigurationChoice(AppBaseModel):
    label: LocalizedString
    description: LocalizedString
    photo_id: Optional[str] = None
    video_id: Optional[str] = None

    existing_presets: bool = Field(default=False)
    existing_presets_chosen: int = 1
    existing_presets_quantity: int = 0

    is_custom_input: bool = Field(default=False)
    custom_input_text: Optional[str] = None
    
    can_be_blocked_by: List[str] = Field(default_factory=list) # формат типо 'option/choice'
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

class ConfigurationOption(AppBaseModel):
    name: LocalizedString
    text: LocalizedString
    photo_id: Optional[str] = None
    video_id: Optional[str] = None
    chosen: str # ConfigurationSwitches нельзя выбрать, это лишь группа выключателей относящейся к целевой опции

    choices: Dict[str, ConfigurationChoice | ConfigurationSwitches]
    
    def get_chosen(self) -> Optional[ConfigurationChoice]:
        return self.choices.get(self.chosen)
    
    def set_chosen(self, choice: ConfigurationChoice):
        self.chosen = next((key for key, value in self.choices.items() if value == choice and isinstance(choice, ConfigurationChoice)), self.chosen)
    
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
                

    def update(self, update_from_option: "ConfigurationOption"):
        self.name = update_from_option.name
        self.text = update_from_option.text
        self.photo_id = update_from_option.photo_id
        self.video_id = update_from_option.video_id
        
        # Обновляем choices
        for choice_key, base_choice in update_from_option.choices.items():
            if choice_key not in self.choices.keys():
                self.choices[choice_key] = base_choice
                continue
            
            self.choices[choice_key].update(base_choice)
        # Удаляем choices, которых больше нет в base
        for choice_key in list(self.choices.keys()):
            if choice_key not in update_from_option.choices:
                del self.choices[choice_key]

class ProductConfiguration(AppBaseModel):
    options: Dict[str, ConfigurationOption]
    additionals: list["ProductAdditional"] = Field(default_factory=list)
    price: Optional[LocalizedMoney] = None
    
    requires_price_confirmation: bool = False
    price_confirmed_override: bool = False
    
    def _sync_price_confirmation_flag(self):
        self.requires_price_confirmation = any(
            hasattr(option.get_chosen(), "blocks_price_determination") and
            option.get_chosen().blocks_price_determination
            for option in self.options.values()
        ) and not self.price_confirmed_override

    def __init__(self, **data):
        super().__init__(**data)
        
        self._sync_price_confirmation_flag()
        if self.price is None: self.update_price()
    
    
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
        
        self._sync_price_confirmation_flag()

    def get_all_options_localized_names(self, lang):
        return [option.name.get(lang) for option in self.options.values()]
    
    def get_option_by_name(self, name, lang) -> Optional[tuple[str, ConfigurationOption]]:
        return next(((key, option) for key, option in self.options.items() 
                     if option.name.get(lang) == name), None)
        
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

class Product(AppBaseModel):
    id: Optional[PydanticObjectId] = None
    name: LocalizedString
    category: str

    short_description: LocalizedString
    short_description_photo_id: str

    long_description: LocalizedString
    long_description_photo_id: Optional[str] = None
    long_description_video_id: Optional[str] = None
    
    base_price: LocalizedMoney
    discount: Optional[Discount] = None

    @property
    def price(self) -> LocalizedMoney:
        return self.base_price - self.discount.get_discount(self.base_price) if self.discount else self.base_price
        

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

    async def get_by_category_and_index(self, category: str, idx: int) -> Optional[Product]:
        ids = await self.get_ids_by_category_sorted_by_date(category)
        if not ids: return None
        
        return await self.find_one_by_id(ids[idx]) if 0 <= idx < len(ids) else None
    
    async def get_name_by_id(self, product_id: PydanticObjectId) -> Optional[LocalizedString]:
        cursor = await self.get_collection().find_one(
            {"_id": product_id},
            projection={"name": 1}
        )
        return LocalizedString(**cursor["name"]) if cursor and "name" in cursor else None
    
    async def count_in_category(self, category) -> int:
        return await self.get_collection().count_documents({"category": category})

class ProductAdditional(AppBaseModel):
    id: Optional[PydanticObjectId] = None
    name: LocalizedString
    category: str

    short_description: LocalizedString

    price: LocalizedMoney
    disallowed_products: list[PydanticObjectId] = Field(default_factory=list)

class AdditionalsRepository(AppAbstractRepository[ProductAdditional]):
    class Meta:
        collection_name = 'additionals'

    async def get(self, product: Product):
        """Возвращает все additionals в категории, которые разрешены для данного продукта."""
        return await self.find_by({"category": product.category, "disallowed_products": {"$nin": [product.id]}})
    
    def get_by_name(self, name, allowed_additionals, lang):
        return next((a for a in allowed_additionals if a.name.get(lang) == name), None)

class Promocode(AppBaseModel):
    id: Optional[PydanticObjectId] = None
    code: str
    action: Discount
    
    description: LocalizedString
    only_newbies: bool

    already_used: int = 0
    max_usages: int = -1

    expire_date: Optional[datetime.datetime] = None

    def __init__(self, **data):
        super().__init__(**data)
        if self.expire_date and self.expire_date.tzinfo is None:
            self.expire_date = self.expire_date.replace(tzinfo=datetime.timezone.utc)

    async def check_promocode(self, customer_orders_amount: int) -> PromocodeCheckResult:
        if self.expire_date and self.expire_date < datetime.datetime.now(datetime.timezone.utc):
            return PromocodeCheckResult.expired
        elif self.only_newbies and customer_orders_amount > 0:
            return PromocodeCheckResult.only_newbies
        elif self.max_usages != -1 and self.max_usages <= self.already_used:
            return PromocodeCheckResult.max_usages_reached
        
        return PromocodeCheckResult.ok

class PromocodesRepository(AppAbstractRepository[Promocode]):
    class Meta:
        collection_name = 'promocodes'
        
    async def get_by_code(self, code: str) -> Optional[Promocode]:
        return await self.find_one_by({"code": code})

class Inviter(AppBaseModel):
    id: Optional[PydanticObjectId] = None
    inviter_code: str

    name: str

class InvitersRepository(AppAbstractRepository[Inviter]):
    class Meta:
        collection_name = 'inviters'

class DeliveryRequirement(AppBaseModel):
    name: LocalizedString
    description: LocalizedString
    value: SecureValue = SecureValue() # для заполнения в будущем при конфигурации

class DeliveryRequirementsList(AppBaseModel):
    name: LocalizedString # типо "По номеру", или "По адресу и ФИО"
    description: LocalizedString
    requirements: list[DeliveryRequirement]

class DeliveryService(AppBaseModel):
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

class DeliveryInfo(AppBaseModel):
    is_foreign: bool = False  # Вне РФ?
    service: Optional[DeliveryService] = None

class Customer(AppBaseModel):
    id: Optional[PydanticObjectId] = None
    user_id: int
    role: str = "default"

    invited_by: str
    kicked: bool = False

    lang: str
    
    currency: str
    bonus_wallet: Money
    delivery_info: Optional[DeliveryInfo] = None
    
    async def change_selected_currency(self, iso: str, acc: AsyncCurrencyConverter):
        """Изменить основную валюту"""
        if iso.upper() not in SUPPORTED_CURRENCIES:
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
            self.bonus_wallet = Money(currency=iso, amount=amount)

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
                bonus_wallet=Money(currency=currency, amount=0.0)
            )
        
        await self.save(customer)
        return customer

    async def get_customer_by_id(self, user_id: int) -> Optional[Customer]:
        return await self.find_one_by({"user_id": user_id})

class Category(AppBaseModel):
    id: Optional[PydanticObjectId] = None
    name: str
    localized_name: LocalizedString

class CategoriesRepository(AppAbstractRepository[Category]):
    class Meta:
        collection_name = 'categories'

    async def get_all(self) -> Optional[Iterable[Category]]:
        return await self.find_by({})
