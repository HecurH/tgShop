from __future__ import annotations
import asyncio
from datetime import datetime, timezone, timedelta
import json
import logging
import re
from typing import Any, Dict, Generic, Type, TypeVar, Optional, List, Iterable, TYPE_CHECKING, Union, cast, get_args

from aiogram.types import Message

from pydantic import BaseModel, Field, field_validator, model_validator

from pymongo import ReplaceOne
from pymongo.results import InsertOneResult, UpdateResult
from pydantic_mongo import AsyncAbstractRepository, PydanticObjectId
from pydantic_mongo.base_abstract_repository import (
    ModelWithId,
    T as TPyMongoModel
)

from core.types.enums import LogType
from registry.currencies import SUPPORTED_CURRENCIES
from registry.payments import SUPPORTED_PAYMENT_METHODS
from configs.referrals import REFERRALS_FIRST_ORDER_PERCENT
from configs.languages import DAYS_BEFORE_CHANGE_CURRENCY
from core.helper_classes import Context
from core.types.values import Discount
from core.types.enums import *
from schemas.entities.payment import PaymentMethod
from core.types.values import *
from ui.translates import EnumTranslates

if TYPE_CHECKING:
    from core.services.db import DatabaseService

T = TypeVar("T")
TModel = TypeVar("TModel", bound="AppBaseModel[Any]")
TDBModel = TypeVar("TDBModel", bound="AppDBModel[Any]")


class AppAbstractRepository(AsyncAbstractRepository[T]):
    def __init__(self, dbs: DatabaseService):
        super().__init__(dbs.db)
        self.dbs = dbs
        
    async def log(self, log_type: LogType, data: str):
        await self.dbs.logs.add_log_entry(log_type, data)
        
    def get_latest_schema_version(self) -> int:
        model_cls = get_args(type(self).__orig_bases__[0])[0]
        return model_cls.latest_schema_version()

    async def check_migrations(self):
        current_version = self.get_latest_schema_version()
        query = {"$or": [
            {"schema_version": {"$exists": False}},
            {"schema_version": {"$lt": current_version}}
        ]}
        
        migrated = await self.find_by(query)
        if len(migrated) == 0:
            return
        
        logging.getLogger(__name__).info(f"Migrating {len(migrated)} documents in {self._collection_name} collection")
        await self.save_many_with_replace(migrated)

    async def save_with_replace(self, model: TPyMongoModel) -> Union[InsertOneResult, UpdateResult]:
        document = self.to_document(model)
        model_with_id = cast(ModelWithId, model)

        if model_with_id.id:
            return await self.get_collection().replace_one(
                {"_id": document.pop("_id")}, document, upsert=True
            )

        result = await self.get_collection().insert_one(document)
        model_with_id.id = result.inserted_id
        return result

    async def save_many_with_replace(self, models: Iterable[TPyMongoModel]):
        models_to_insert = []
        models_to_update = []

        for model in models:
            model_with_id = cast(ModelWithId, model)
            if model_with_id.id:
                models_to_update.append(model)
            else:
                models_to_insert.append(model)
        if len(models_to_insert) > 0:
            result = await self.get_collection().insert_many(
                (self.to_document(model) for model in models_to_insert)
            )

            for idx, inserted_id in enumerate(result.inserted_ids):
                cast(ModelWithId, models_to_insert[idx]).id = inserted_id

        if len(models_to_update) == 0:
            return

        documents_to_update = [self.to_document(model) for model in models_to_update]
        mongo_ids = [doc.pop("_id") for doc in documents_to_update]
        bulk_operations = [
            ReplaceOne({"_id": mongo_id}, document, upsert=True)
            for mongo_id, document in zip(mongo_ids, documents_to_update)
        ]
        await self.get_collection().bulk_write(bulk_operations, ordered=False)
        
# класс BaseModel, но со своей функцией для загрузки сериализованных объектов
class AppBaseModel(BaseModel, Generic[TModel]):
    @classmethod
    async def from_fsm_context(cls: Type[TModel], ctx: Context, key: str, default: Optional[TModel] = None) -> Optional[TModel | list[TModel]]:
        """Загрузка напрямую из контекста по ключу"""
        value: Optional[dict | list[dict]] = await ctx.fsm.get_value(key)
        if not value: return default
        
        if isinstance(value, dict):
            return cls(**value)
        elif isinstance(value, list):
            return [cls(**entry) for entry in value]
        else:
            return default
    
    @classmethod
    async def save_many_in_fsm(cls: Type[TModel], ctx: Context, key: str, models: Iterable[TModel]):
        """Сохранение нескольких моделей в FSM"""
        dumped_list = [model.model_dump() for model in models]
        await ctx.fsm.update_data({key: dumped_list})
    
    async def save_in_fsm(self, ctx: Context, key: str):
        """Сохранение в контекст по ключу"""
        await ctx.fsm.update_data({key: self.model_dump()})
        
class AppDBModel(AppBaseModel[TModel]):
    schema_version: int = 0
    
    @model_validator(mode="before")
    @classmethod
    def _base_migrate(cls, data: dict):
        if not isinstance(data, dict):
            return data
        if "schema_version" not in data:
            data["schema_version"] = 0
        return data
    
    
    @classmethod
    def latest_schema_version(cls) -> int:
        schema_version = cls.model_fields.get("schema_version")
        return schema_version.default if schema_version else 0
    
class LogEntry(AppDBModel):
    id: Optional[PydanticObjectId] = None
    log_lype: LogType
    
    data: str
    created_at: datetime
    
class LogsRepository(AppAbstractRepository[LogEntry]):
    class Meta:
        collection_name = 'logs'
        
    async def add_log_entry(self, log_type: LogType, data: str):
        entry = LogEntry(log_lype=log_type, 
                         data=data, 
                         created_at=datetime.now(timezone.utc))
        
        await self.save(entry)
         
class Placeholder(AppDBModel):
    id: Optional[PydanticObjectId] = None
    
    key: str
    value: LocalizedString
    
class PlaceholdersRepository(AppAbstractRepository[Placeholder]):
    class Meta:
        collection_name = 'placeholders'
        
    async def find_by_key(self, key: str) -> Optional[Placeholder]:
        return await self.find_one_by({'key': key})
    
    async def get_all(self) -> List[Placeholder]:
        return list(await self.find_by({}))

class OrderPriceDetails(AppBaseModel):
    products_price: Money  # сумма товаров без скидок и доставки
    promocode_discount: Optional[Money] = None  # скидка по промокоду
    
    delivery_price: Optional[Money] = None  # доставка
    bonuses_applied: Optional[Money] = None # сколько бонусных средств для оплаты
    
    total_price: Optional[Money] = None  # сколько надо заплатить настоящими деньгами
    
    customer_paid: bool = False
    payment_time: Optional[datetime] = None
    
    @classmethod
    def new(cls, customer: Customer, products_price: LocalizedMoney, delivery_info: DeliveryInfo = None) -> OrderPriceDetails:
        price_details = OrderPriceDetails(products_price=products_price.get_money(customer.currency),
                                          delivery_price=delivery_info.service.price.get_money(customer.currency) if delivery_info else None
                                          )
        price_details.recalculate_price()
        return price_details
    

    def recalculate_price(self):
        products_price_after_promocode = (self.products_price - self.promocode_discount) if self.promocode_discount else self.products_price
        total = products_price_after_promocode + self.delivery_price if self.delivery_price else products_price_after_promocode
        
        self.total_price = total - self.bonuses_applied if self.bonuses_applied else total
    
    async def get_referral_reward(self) -> Optional[Money]:
        if not self.total_price: return None
        reward = self.total_price * REFERRALS_FIRST_ORDER_PERCENT
        return reward

class OrderState(BaseModel):
    key: OrderStateKey
    comment: list[SavedTMessage] = Field(default_factory=list)

    def get_localized_name(self, lang: str) -> str:
        return EnumTranslates.OrderStateKey.translate(self.key.value, lang)
    
    def set_state(self, key: OrderStateKey):
        self.key = key 
        
    def add_comment(self, message: Message) -> SavedTMessage:
        tmsg = SavedTMessage(chat_id=message.chat.id, message_id=message.message_id)
        self.comment.append(tmsg)
        return tmsg
        
    def get_comments(self):
        return self.comment
    
    def __eq__(self, value):
        return self.key == value    

class Order(AppDBModel):
    id: Optional[PydanticObjectId] = None
    puid: Optional[str] = None
    number: Optional[int] = None
    
    customer_id: PydanticObjectId
    state: OrderState = OrderState(key=OrderStateKey.forming)
    delivery_info: Optional[DeliveryInfo] = None # при запросе удаления перс данных, обычно не должен быть пуст

    promocode_id: Optional[PydanticObjectId] = None

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
        self.price_details.promocode_discount = promocode.discount.get_discount(self.price_details.products_price) if promocode else None
        self.price_details.recalculate_price()
        
        self.promocode_id = promocode.id if promocode else None
    
    async def update_applied_bonuses(self, customer_bonus_balance: Optional[Money]):
        if not customer_bonus_balance:
            self.price_details.bonuses_applied = None
            self.price_details.recalculate_price()
            return
        
        price_details = self.price_details
        products_price_after_promocode = (price_details.products_price - price_details.promocode_discount) if price_details.promocode_discount else price_details.products_price
        total = products_price_after_promocode + price_details.delivery_price
        
        self.price_details.bonuses_applied = min(total, customer_bonus_balance)
        self.price_details.recalculate_price()

class OrdersRepository(AppAbstractRepository[Order]):
    class Meta:
        collection_name = 'orders'
        
    def __init__(self, dbs: DatabaseService):
        super().__init__(dbs)
        
        self.logger = logging.getLogger(__name__)
        
    def new_order(self, customer: Customer, products_price: LocalizedMoney, save_delivery_info: bool = True) -> Order:
        delivery_info = customer.privacy_data.delivery_info if save_delivery_info else None
        price_details = OrderPriceDetails.new(customer, products_price, delivery_info)
        
        return Order(customer_id=customer.id, delivery_info=delivery_info, price_details=price_details)
    
    async def find_customer_orders(self, customer: Customer) -> Iterable[Order]:
        return await self.find_by({"customer_id": customer.id})
    
    async def find_by_puid(self, puid: str, customer: Optional[Customer] = None) -> Optional[Order] | Iterable[Order]:
        if customer:
            return await self.find_one_by({"puid": puid, "customer_id": customer.id})
        else:
            return await self.find_by({"puid": puid})
        
    async def count_customer_orders(self, customer: Customer) -> int:
        return await self.get_collection().count_documents({"customer_id": customer.id})
    
    async def count_formed_customer_orders(self, customer: Customer) -> int:
        return await self.get_collection().count_documents({"customer_id": customer.id, "state.key": {"$ne": OrderStateKey.waiting_for_forming.name}})
    
    async def save(self, order: Order):
        order.number = order.number or await self.dbs.get_next_for_counter(self.Meta.collection_name)
        
        # puid только для нового заказа
        if not order.id:
            result = await super().save(order)
            inserted_id = str(result.inserted_id)
            
            order.id = PydanticObjectId(inserted_id)
            order.puid = Order.generate_puid(inserted_id)
            self.logger.info(f"New order {order.id} for customer {order.customer_id}")
            
        await super().save(order)

# class CartEntryOLD(AppBaseModel):
#     id: Optional[PydanticObjectId] = None
#     customer_id: PydanticObjectId
#     product_id: PydanticObjectId
    
#     frozen_product: Optional[Product] = None # только для сформированных заказов
    
#     order_id: Optional[PydanticObjectId] = None

#     quantity: int = Field(default=1, gt=0)

#     configuration: "ProductConfiguration"
    
#     @property
#     def need_to_confirm_price(self) -> bool:
#         return self.configuration.requires_price_confirmation
    
class CartEntry(AppDBModel):
    id: Optional[PydanticObjectId] = None
    customer_id: PydanticObjectId
    order_id: Optional[PydanticObjectId] = None

    source_type: CartItemSource = CartItemSource.product
    source_id: PydanticObjectId  # product.id ИЛИ discounted_product.id

    frozen_snapshot: Optional[Product | DiscountedProduct] = None # DiscountedProduct сразу фризится

    quantity: int = Field(default=1, gt=0)
    configuration: Optional["ProductConfiguration"] = None
    
    @model_validator(mode="before")
    @classmethod
    def from_v1(cls, data: dict):
        if not isinstance(data, dict):  # уже готовый объект — пропускаем
            return data
        
        if "source_type" in data:
            return data

        if "product_id" in data:
            logging.getLogger(__name__).warning("CartEntry: converting from v1 to v2")
            
            data["source_type"] = CartItemSource.product
            data["source_id"] = data.pop("product_id")

            if "frozen_product" in data:
                data["frozen_snapshot"] = data.pop("frozen_product")

        return data
    
    @model_validator(mode="before")
    @classmethod
    def resolve_snapshot(cls, data: dict):
        if not isinstance(data, dict):  # уже готовый объект — пропускаем
            return data
        
        snapshot = data.get("frozen_snapshot")
        source_type = data.get("source_type")
        
        if isinstance(snapshot, dict) and source_type:
            if source_type == CartItemSource.discounted or source_type == "discounted":
                data["frozen_snapshot"] = DiscountedProduct(**snapshot)
            elif source_type == CartItemSource.product or source_type == "product":
                data["frozen_snapshot"] = Product(**snapshot)
        
        return data
    
    @field_validator("quantity")
    @classmethod
    def force_quantity_for_discounted(cls, v, info):
        if info.data.get("source_type") == CartItemSource.discounted:
            return 1
        return v
    
    @property
    def need_to_confirm_price(self) -> bool:
        return self.configuration.requires_price_confirmation if self.configuration else False
    
    def calculate_price(self, product: Optional[Product] = None, multiply_quantity: bool = True) -> LocalizedMoney:
        if self.source_type == CartItemSource.product:
            price = self.configuration.price + product.price
            return price * self.quantity if multiply_quantity else price
        elif self.source_type == CartItemSource.discounted:
            return self.frozen_snapshot.price

class CartEntriesRepository(AppAbstractRepository[CartEntry]):
    class Meta:
        collection_name = 'cart_entries'
    
    def __init__(self, dbs: DatabaseService):
        super().__init__(dbs)
        
        self.logger = logging.getLogger(__name__)
        
    
    async def add_to_cart(self, source: Product | DiscountedProduct, customer: Customer):
        is_product = isinstance(source, Product)

        await self.save(CartEntry(customer_id=customer.id, 
                                  source_type=CartItemSource.product if is_product else CartItemSource.discounted,
                                  source_id=source.id,
                                  frozen_snapshot=None if is_product else source,
                                  configuration=source.configuration if is_product else None))
        
        self.logger.info(f"Added {source.name.get('ru')} to cart for {customer.user_id}")
        
    async def check_product_in_cart(self, product: Product | DiscountedProduct, customer: Customer) -> bool:
        return await self.get_collection().count_documents({"customer_id": customer.id, 
                                                            "order_id": None,
                                                            "source_id": product.id}) > 0
        
    async def check_product_in_orders(self, product: Product | DiscountedProduct, customer: Customer) -> bool:
        return await self.get_collection().count_documents({"customer_id": customer.id, 
                                                            "order_id": {"$ne": None},
                                                            "source_id": product.id}) > 0
        
    async def delete_discounted_product_from_carts(self, discounted_product_id: PydanticObjectId):
        entries = await self.find_by({"order_id": None, 
                            "source_type": CartItemSource.discounted,
                            "source_id": discounted_product_id})
        for entry in entries:
            await self.delete(entry)
        
    async def count_customer_cart_entries(self, customer: Customer):
        return await self.get_collection().count_documents({"customer_id": customer.id, "order_id": None})
    
    async def find_customer_cart_ids_sorted_by_date(self, customer: Customer) -> List[PydanticObjectId]:
        """Получить список id продуктов в категории, отсортированных по дате создания (ObjectId)."""
        cursor = self.get_collection().find(
            {"customer_id": customer.id,
             "order_id": None},
            projection={"_id": 1}
        ).sort("_id", 1)
        return [PydanticObjectId(doc["_id"]) async for doc in cursor]

    async def find_customer_cart_entries(self, customer: Customer, query: Optional[dict] = None) -> Iterable[CartEntry]:
        base_query = {**(query or {}), "customer_id": customer.id, "order_id": None}
        return await self.find_by(base_query, sort=[("_id", 1)])
    
    async def find_entries_by_order(self, order: Order, query: Optional[dict] = None) -> Iterable[CartEntry]:
        base_query = {**(query or {}), "order_id": order.id}
        return await self.find_by(base_query, sort=[("_id", 1)])
    
    async def find_entries_by_product(self, product: Product | DiscountedProduct, query: Optional[dict] = None) -> Iterable[CartEntry]:
        base_query = {**(query or {}), "source_id": product.id}
        return await self.find_by(base_query, sort=[("_id", 1)])

    async def find_customer_cart_entry_by_id(self, customer: Customer, idx: int) -> Optional[CartEntry]:
        ids = await self.find_customer_cart_ids_sorted_by_date(customer)
        if not ids: return None
        
        return await self.find_one_by_id(ids[idx]) if 0 <= idx < len(ids) else None
        
    async def assign_cart_entries_to_order(self, customer: Customer, order: Order):
        entries = await self.find_customer_cart_entries(customer)
        
        if not entries:
            return
        
        product_ids = [entry.source_id for entry in entries if entry.source_type == CartItemSource.product]
        
        products = (
            await self.dbs.products.find_by({"_id": {"$in": product_ids}})
            if product_ids else []
        )
        
        products_map = {product.id: product for product in products}
        
        for entry in entries:
            entry.order_id = order.id
            if entry.source_type == CartItemSource.product:
                entry.frozen_snapshot = products_map.get(entry.source_id)
            
        await self.save_many(entries)
        
    async def unassign_cart_entries_from_order(self, order: Order):
        entries = await self.find_entries_by_order(order)
        if not entries:
            return

        for entry in entries:
            entry.order_id = None
            if entry.source_type == CartItemSource.product:
                entry.frozen_snapshot = None
            # elif entry.source_type == CartItemSource.discounted:
            #     await self.delete(entry)
        
        await self.save_many(entries)
        
    async def update_product_in_carts(self, product: Product, additionals: Iterable[ProductAdditional]):
        entries = await self.find_entries_by_product(product)
        for entry in entries:
            entry.configuration.update(product.configuration, additionals)

        await self.save_many(entries)
    
    async def calculate_customer_cart_price(self, customer: Customer) -> LocalizedMoney:
        entries: Iterable[CartEntry] = await self.find_by({"customer_id": customer.id, "order_id": None})
        products: Iterable[Product] = await self.dbs.products.find_by({"_id": {"$in": [entry.source_id for entry in entries if entry.source_type == CartItemSource.product]}})
        product_map: Dict[PydanticObjectId, Product] = {
            product.id: product for product in products
        }

        total_price = LocalizedMoney()
        for entry in entries:
            if entry.source_type == CartItemSource.product and (product := product_map.get(entry.source_id)):
                total_price += entry.calculate_price(product)
            if entry.source_type == CartItemSource.discounted:
                total_price += entry.calculate_price()
        return total_price

    async def calculate_cart_entries_price_by_order(self, order: Order) -> LocalizedMoney:
        entries: Iterable[CartEntry] = await self.find_by({"order_id": order.id})
        products: Iterable[Product] = await self.dbs.products.find_by({"_id": {"$in": [entry.source_id for entry in entries if entry.source_type == CartItemSource.product]}})
        product_map: Dict[PydanticObjectId, Product] = {
            product.id: product for product in products
        }

        total_price = LocalizedMoney()
        for entry in entries:
            if entry.source_type == CartItemSource.product and (product := product_map.get(entry.source_id)):
                entry_total = (product.price + entry.configuration.price) * entry.quantity
                total_price += entry_total
            if entry.source_type == CartItemSource.discounted:
                total_price += entry.frozen_snapshot.price * entry.quantity
        return total_price
    
    async def check_price_confirmation_in_cart(self, customer: Customer) -> bool:
        query = {
            "customer_id": customer.id,
            "order_id": None,
            "configuration.requires_price_confirmation": True
        }

        document = await self.get_collection().find_one(query, projection={"_id": 1})
        return document is not None
    
    async def find_price_confirmation_entries(self, order: Order) -> Iterable[CartEntry]:
        query = {
            "order_id": order.id,
            "configuration.requires_price_confirmation": True
        }

        return await self.find_by(query)

class DiscountedProduct(AppDBModel):
    id: Optional[PydanticObjectId] = None
    name: LocalizedString
    
    description: LocalizedString
    media: Optional[LocalizedSavedMedia] = None
    
    price: LocalizedMoney
    
    reserved: bool = False

class DiscountedProductsRepository(AppAbstractRepository[DiscountedProduct]):
    class Meta:
        collection_name = 'discounted_products'
        
    async def count(self) -> int:
        return await self.get_collection().count_documents({})
    
    async def find_by_index(self, idx: int) -> Optional[Product]:
        cursor = self.get_collection().find(
            {},
            projection={"_id": 1}
        ).sort("_id", 1)
        
        ids = [PydanticObjectId(doc["_id"]) async for doc in cursor]
        if not ids: return None
        
        return await self.find_one_by_id(ids[idx]) if 0 <= idx < len(ids) else None
    
    async def check_reserved(self, product_id: PydanticObjectId | list[PydanticObjectId]) -> bool:
        if isinstance(product_id, list):
            query = {"_id": {"$in": product_id}, "reserved": True}
        else:
            query = {"_id": product_id, "reserved": True}
        
        return await self.get_collection().count_documents(query) > 0
    
    async def set_reserved(self, product_id: PydanticObjectId | list[PydanticObjectId], reserved: bool):
        if isinstance(product_id, list):
            products = await self.find_by({"_id": {"$in": product_id}})
            if not products: return
            
            for product in products:
                product.reserved = reserved
                
            await self.save_many(products)
        elif isinstance(product_id, PydanticObjectId):
            product = await self.find_one_by_id(product_id)
            if not product: return
            
            product.reserved = reserved
            
            await self.save(product)

class ConfigurationSwitch(AppBaseModel):
    name: LocalizedEntry
    description: Optional[LocalizedEntry] = None
    
    price: LocalizedMoney = Field(default_factory=lambda: LocalizedMoney.empty_base())
    can_be_blocked_by: List[str] = Field(default_factory=list)

    enabled: bool = False
    
    def toggle(self):
        self.enabled = not self.enabled
    
    def update(self, base_sw: "ConfigurationSwitch"):
        self.name=base_sw.name
        self.price=base_sw.price
        
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
    
    def check_blocked_path(self, path: str, options: Dict[str, "ConfigurationOption"]) -> bool:
        keys = path.split("/")
        
        option = options.get(keys[0]) if keys else None
        if not option: raise Exception("BPath: No such option")
        
        chosen_key = option.chosen_key
        if chosen_key == keys[1] and len(keys) == 2:
            return True
        
        chosen = option.get_chosen()
        if isinstance(chosen, ConfigurationSwitches) and len(keys) > 2:
            keys = keys[2:]
            
            switch_or_group = chosen.switches.get(keys[0])
            if not switch_or_group: raise Exception("BPath: No such switch")
            if isinstance(switch_or_group, ConfigurationSwitch): return switch_or_group.enabled
            elif isinstance(switch_or_group, ConfigurationSwitchesGroup):
                if len(keys) != 2: raise Exception("BPath: Wrong switch group path")
                switch = switch_or_group.switches.get(keys[1])
                if not switch: raise Exception("BPath: No such switch")
                return switch.enabled
        return False
        
class ConfigurationSwitchesGroup(AppBaseModel):
    name: LocalizedEntry
    description: LocalizedEntry
    switches: Dict[str, ConfigurationSwitch]
    
    def get_all(self):
        return self.switches.values()
    
    def get_enabled(self):
        """Возвращает список включённых переключателей из списка switches."""
        return [switch for switch in self.switches.values() if switch.enabled]
    
    def update(self, base_grp: "ConfigurationSwitchesGroup"):
        self.name=base_grp.name
        self.description=base_grp.description
        
        for key, switch in base_grp.switches.items():
            if key not in self.switches:
                self.switches[key] = switch
                continue
            self.switches[key].update(switch)

class ConfigurationSwitches(AppBaseModel):
    name: LocalizedEntry
    description: LocalizedEntry
    media: Optional[LocalizedSavedMedia] = None

    switches: Dict[str, ConfigurationSwitch | ConfigurationSwitchesGroup]

    def get_all(self):
        return self.switches.values()
    
    def get_enabled(self):
        """Возвращает список включённых переключателей из списка switches."""
        enabled_switches = []
        for switch in self.switches.values():
            if isinstance(switch, ConfigurationSwitch) and switch.enabled:
                enabled_switches.append(switch)
            elif isinstance(switch, ConfigurationSwitchesGroup):
                enabled_switches.extend(switch.get_enabled())
        return enabled_switches
    
    def calculate_price_for_enabled(self):
        """Возвращает сумму цен всех включённых переключателей."""
        return sum((switch.price for switch in self.get_enabled()), LocalizedMoney())
    
    def get_by_localized_name(self, name, ctx):
        for switch in self.get_all():
            if isinstance(switch, ConfigurationSwitchesGroup):
                for sw in switch.get_all():
                    if sw.name.get(ctx) == name:
                        return sw
            elif switch.name.get(ctx) == name:
                return switch

    def update(self, update_from_switches: "ConfigurationSwitches"):
        self.name = update_from_switches.name
        self.description = update_from_switches.description
        self.media = update_from_switches.media
        
        for key, updated_switch_or_group in update_from_switches.switches.items():
            switch_or_group = self.switches[key]
            if key not in self.switches:
                switch_or_group = updated_switch_or_group
                continue
            if type(switch_or_group) == type(updated_switch_or_group):
                switch_or_group.update(updated_switch_or_group)
            else:
                self.switches[key] = updated_switch_or_group

class ConfigurationChoice(AppBaseModel):
    name: LocalizedEntry
    description: LocalizedEntry
    media: Optional[LocalizedSavedMedia] = None

    existing_presets: bool = Field(default=False)
    existing_presets_pattern: str = "int"
    existing_presets_chosen: str = ""
    price_by_preset: Optional[Dict[str, LocalizedMoney]] = None

    is_custom_input: bool = Field(default=False)
    custom_input_text: Optional[str] = None
    
    can_be_blocked_by: List[str] = Field(default_factory=list) # формат типо 'option/choice'
    blocks_price_determination: bool = Field(default=False)
    price: LocalizedMoney = Field(default_factory=lambda: LocalizedMoney.empty_base())
    
    def update(self, base_choice: "ConfigurationChoice"):
        self.name=base_choice.name
        self.description=base_choice.description
        self.media=base_choice.media
        self.existing_presets_pattern=base_choice.existing_presets_pattern
        self.existing_presets=base_choice.existing_presets
        self.is_custom_input=base_choice.is_custom_input
        self.blocks_price_determination=base_choice.blocks_price_determination
        self.price_by_preset = base_choice.price_by_preset
        
        if self.price_by_preset:
            self.set_chosen_preset(self.existing_presets_chosen)
        else:
            self.price=base_choice.price
    
    def set_chosen_preset(self, preset: str):
        if self.price_by_preset and self.validate_existing_preset(preset):
            self.existing_presets_chosen = preset
            
            total_price = LocalizedMoney.empty_base()
            for let, price in self.price_by_preset.items():
                if let in preset:
                    total_price += price
            self.price = total_price
                    
    
    def validate_existing_preset(self, text) -> bool:
        parts = self.existing_presets_pattern.split('|')
        regex_parts = []

        for part in parts:
            if part == 'int':
                regex_parts.append(r'\d+')
            elif ',' in part:
                options = part.split(',')
                regex_parts.append(f"[{''.join(options)}]")
            else:
                regex_parts.append(re.escape(part))

        pattern = '^' + ''.join(regex_parts) + '$'

        return bool(re.compile(pattern).match(text))
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
    
    def check_blocked_path(self, path: str, options: Dict[str, "ConfigurationOption"]) -> bool:
        keys = path.split("/")
        
        option = options.get(keys[0]) if keys else None
        if not option: raise Exception("BPath: No such option")
        
        chosen_key = option.chosen_key
        if chosen_key == keys[1] and len(keys) == 2:
            return True
        
        if len(keys) > 2:
            keys = keys[2:]
            for switches in [val.switches for val in option.choices.values() if isinstance(val, ConfigurationSwitches)]:
                switch_or_group = switches.get(keys[0])
                if not switch_or_group: raise Exception("BPath: No such switch")
                if isinstance(switch_or_group, ConfigurationSwitch): return switch_or_group.enabled
                elif isinstance(switch_or_group, ConfigurationSwitchesGroup):
                    if len(keys) != 2: raise Exception("BPath: Wrong switch group path")
                    switch = switch_or_group.switches.get(keys[1])
                    if not switch: raise Exception("BPath: No such switch")
                    return switch.enabled
        return False

class ConfigurationAnnotation(AppBaseModel):
    name: LocalizedEntry
    text: LocalizedEntry
    media: Optional[LocalizedSavedMedia] = None
    
    def update(self, base_annotation: "ConfigurationAnnotation"):
        self.name=base_annotation.name
        self.text=base_annotation.text
        self.media=base_annotation.media

class ConfigurationOption(AppBaseModel):
    name: LocalizedEntry
    text: LocalizedEntry
    chosen_key: str # ConfigurationSwitches нельзя выбрать, это лишь группа выключателей относящейся к целевой опции

    choices: Dict[str, ConfigurationChoice | ConfigurationSwitches | ConfigurationAnnotation]
    
    def get_chosen(self) -> Optional[ConfigurationChoice]:
        choice = self.choices.get(self.chosen_key) or list(self.choices.values())[0] if self.choices else None
        
        return choice if isinstance(choice, ConfigurationChoice) else None
    
    def set_chosen(self, choice: ConfigurationChoice):
        self.chosen_key = next((key for key, value in self.choices.items() if value == choice and isinstance(choice, ConfigurationChoice)), self.chosen_key)
    
    def get_key_by_name(self, name: str, ctx: Context) -> Optional[str]:
        for key, choice in self.choices.items():
            if hasattr(choice, "name") and choice.name.get(ctx) == name:
                return key
    
    def get_by_name(self, name: str, ctx: Context) -> Optional[ConfigurationChoice | ConfigurationSwitches]:
        for choice in self.choices.values():
            if hasattr(choice, "name") and choice.name.get(ctx) == name:
                return choice

    def calculate_price(self):
        conf_choice = self.get_chosen().model_copy(deep=True)
        price = conf_choice.price.model_copy(deep=True) if isinstance(conf_choice, ConfigurationChoice) else LocalizedMoney()
        price += sum((choice.calculate_price_for_enabled() for choice in self.choices.values() if isinstance(choice, ConfigurationSwitches)), LocalizedMoney())
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
        
        # Обновляем choices
        for choice_key, base_choice in update_from_option.choices.items():
            if choice_key not in self.choices.keys():
                self.choices[choice_key] = base_choice
                continue
            
            cur_choice = self.choices[choice_key]
            
            if type(cur_choice) == type(base_choice):
                cur_choice.update(base_choice)
            else:
                self.choices[choice_key] = base_choice
        # Удаляем choices, которых больше нет в base
        for choice_key in list(self.choices.keys()):
            if choice_key not in update_from_option.choices:
                del self.choices[choice_key]

class ProductConfiguration(AppBaseModel):
    options: Dict[str, ConfigurationOption | ConfigurationAnnotation]
    additionals: list["ProductAdditional"] = Field(default_factory=list)
    price: Optional[LocalizedMoney] = None
    
    requires_price_confirmation: bool = False
    price_confirmed_override: bool = False
    
    def _sync_price_confirmation_flag(self):
        new_value = any(
            hasattr(option.get_chosen(), "blocks_price_determination") and
            option.get_chosen().blocks_price_determination
            for option in self.get_options().values()
        ) and not self.price_confirmed_override
        
        if self.requires_price_confirmation != new_value:
            super().__setattr__('requires_price_confirmation', new_value)

    def __init__(self, **data):
        super().__init__(**data)
        
        self._sync_price_confirmation_flag()
        if self.price is None: self.update_price()
        
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        
        if name in ["options", "price_confirmed_override"]:
            if self.options: self._sync_price_confirmation_flag()
    
    def get_options(self, only_options: bool = True):
        if only_options:
            return {key: option for key, option in self.options.items() if isinstance(option, ConfigurationOption)}
        else:
            return self.options
    
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
        
        self.update_price()
        self._sync_price_confirmation_flag()
        

    def get_all_options_localized_names(self, ctx: Context):
        return [option.name.get(ctx) for option in self.options.values()]
    
    def get_option_by_name(self, name, ctx: Context) -> Optional[tuple[str, ConfigurationOption]]:
        return next(((key, option) for key, option in self.options.items() 
                     if option.name.get(ctx) == name), None)
        
    def get_price_blocking_options(self) -> dict[str, ConfigurationOption]:
        return {key: option for key, option in self.get_options().items() if option.get_chosen().blocks_price_determination}
        
    def get_additionals_ids(self) -> Iterable[PydanticObjectId]:
        return [add.id for add in self.additionals]
    
    def get_localized_names_by_path(self, path, ctx: Context) -> List[str]:
        keys = path.split("/")
        result = []
        option_key = keys[0] if keys else None
        choice_key = keys[1] if len(keys) > 1 else None
        switch_or_group_key = keys[2] if len(keys) > 2 else None
        group_switch_key = keys[3] if len(keys) == 4 else None
        
        # Получаем опцию
        option = self.options.get(option_key) if option_key else None
        if not option:
            raise Exception("BPath: No such option")
        # Добавляем имя опции
        result.append(option.name.get(ctx))
        # Получаем выбор
        choice = option.choices.get(choice_key) if choice_key else None
        if not choice:
            raise Exception("BPath: Where is my choice")
        # Добавляем имя выбора
        if isinstance(choice, ConfigurationChoice): result.append(choice.name.get(ctx))
        # Если есть переключатель (switch)
        else:
            switch_or_group = choice.switches.get(switch_or_group_key)
            if switch_or_group is not None:
                if isinstance(switch_or_group, ConfigurationSwitch):
                    result.append(switch_or_group.name.get(ctx))
                elif isinstance(switch_or_group, ConfigurationSwitchesGroup):
                    if switch := switch_or_group.switches.get(group_switch_key):
                        result.append(switch.name.get(ctx))
                
        return result
        
    def calculate_additionals_price(self):
        return sum((additional.price.model_copy(deep=True) for additional in self.additionals), LocalizedMoney())
    
    def calculate_options_price(self):
        return sum((option.calculate_price() for option in self.get_options().values()), LocalizedMoney())
    
    def update_price(self):
        self.price = self.calculate_additionals_price() + self.calculate_options_price()

class Product(AppDBModel):
    id: Optional[PydanticObjectId] = None
    name: LocalizedString
    name_for_tax: str
    
    category: str
    
    description: LocalizedString
    description_media: Optional[LocalizedSavedMedia] = None
    
    visible: bool = True
    
    base_price: LocalizedMoney
    discount: Optional[Discount] = None

    @property
    def price(self) -> LocalizedMoney:
        return self.base_price - self.discount.get_discount(self.base_price) if self.discount else self.base_price
        

    configuration: ProductConfiguration
    configuration_media: Optional[LocalizedSavedMedia] = None
    
    
    @model_validator(mode="before")
    @classmethod
    def from_v1(cls, data: dict):
        if not isinstance(data, dict):  # уже готовый объект — пропускаем
            return data
        
        if "description" in data and "visible" in data:
            return data
        
        logging.getLogger(__name__).warning("Product: converting from v1 to v2")

        if "short_description_media" in data:
            
            
            data.pop("short_description")
            data.pop("short_description_media")
            data["description"] = data.pop("long_description")
            data["description_media"] = data.pop("long_description_media")
        
        if "visible" not in data:
            data["visible"] = True

        return data
    
    
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
    
    async def get_ids_by_category_sorted_by_date(self, category: str, only_visible: bool = True) -> List[PydanticObjectId]:
        """Получить список id продуктов в категории, отсортированных по дате создания (ObjectId)."""
        f = {"category": category, "visible": True} if only_visible else {"category": category}
        
        cursor = self.get_collection().find(
            f,
            projection={"_id": 1}
        ).sort("_id", 1)
        return [PydanticObjectId(doc["_id"]) async for doc in cursor]
    
    async def find_by_entries(self, entries: List[CartEntry]) -> Iterable[Product]:
        ids = [entry.source_id for entry in entries if entry.source_type == CartItemSource.product]
        return (
            await self.find_by({"_id": {"$in": ids}})
            if ids else []
        )

    async def find_by_category_and_index(self, category: str, idx: int, only_visible: bool = True) -> Optional[Product]:
        ids = await self.get_ids_by_category_sorted_by_date(category, only_visible=only_visible)
        if not ids: return None
        
        return await self.find_one_by_id(ids[idx]) if 0 <= idx < len(ids) else None
    
    async def get_name_by_id(self, product_id: PydanticObjectId) -> Optional[LocalizedString]:
        cursor = await self.get_collection().find_one(
            {"_id": product_id},
            projection={"name": 1}
        )
        return LocalizedString(**cursor["name"]) if cursor and "name" in cursor else None
    
    async def count_in_category(self, category, only_visible: bool = True) -> int:
        f = {"category": category, "visible": True} if only_visible else {"category": category}
        
        return await self.get_collection().count_documents(f)

class ProductAdditional(AppDBModel):
    id: Optional[PydanticObjectId] = None
    name: LocalizedString
    category: str

    description: Optional[LocalizedString] = None

    price: LocalizedMoney
    disallowed_products: list[PydanticObjectId] = Field(default_factory=list)

class AdditionalsRepository(AppAbstractRepository[ProductAdditional]):
    class Meta:
        collection_name = 'additionals'

    async def get(self, product: Product):
        """Возвращает все additionals в категории, которые разрешены для данного продукта."""
        return await self.find_by({"category": product.category, "disallowed_products": {"$nin": [product.id]}})
    
    def get_by_name(self, name, allowed_additionals, ctx: Context):
        return next((a for a in allowed_additionals if a.name.get(ctx) == name), None)

class Promocode(AppDBModel):
    id: Optional[PydanticObjectId] = None
    code: str
    discount: Discount
    
    description: LocalizedString
    only_newbies: bool = False

    already_used: int = 0
    max_usages: int = -1

    expire_date: Optional[datetime] = None

    def __init__(self, **data):
        super().__init__(**data)
        if self.expire_date and self.expire_date.tzinfo is None:
            self.expire_date = self.expire_date.replace(tzinfo=timezone.utc)

    def check_promocode(self, customer_orders_amount: Optional[int] = None) -> PromocodeCheckResult:
        if self.expire_date and self.expire_date < datetime.now(timezone.utc):
            return PromocodeCheckResult.expired
        elif self.only_newbies and customer_orders_amount and customer_orders_amount > 0:
            return PromocodeCheckResult.only_newbies
        elif self.max_usages != -1 and self.max_usages <= self.already_used:
            return PromocodeCheckResult.max_usages_reached
        
        return PromocodeCheckResult.ok

class PromocodesRepository(AppAbstractRepository[Promocode]):
    class Meta:
        collection_name = 'promocodes'
        
    async def find_by_code(self, code: str) -> Optional[Promocode]:
        return await self.find_one_by({"code": code})
    
    async def get_all(self) -> Iterable[Promocode]:
        return await self.find_by({})
    
    async def update_usage(self, promocode_id: PydanticObjectId, upd: int = 1):
        promocode = await self.find_one_by_id(promocode_id)
        if not promocode: return
        if promocode.max_usages != -1 and (promocode.max_usages < promocode.already_used + upd):
            raise ValueError("Promocode max usages reached")

        promocode.already_used += upd
        await self.save(promocode)

class Inviter(AppDBModel):
    id: Optional[PydanticObjectId] = None
    
    customer_id: PydanticObjectId
    inviter_type: InviterType = InviterType.customer
    
    invited_customers: int = 0
    invited_customers_first_orders: int = 0
    
    async def gen_link(self, ctx: Context) -> str:
        me = await ctx.message.bot.get_me()
        return f"https://t.me/{me.username}?start=inviter_{str(self.id)}"

class InvitersRepository(AppAbstractRepository[Inviter]):
    class Meta:
        collection_name = 'inviters'
        
    async def check_customer(self, customer_id: PydanticObjectId) -> bool:
        return await self.get_collection().count_documents({"customer_id": customer_id}) > 0
    
    async def find_by_customer_id(self, customer_id: PydanticObjectId) -> Optional[Inviter]:
        return await self.find_one_by({"customer_id": customer_id})
    
    async def find_inviter_by_deep_link(self, deep_link: str) -> Optional[Inviter]:
        try:
            if "_" not in deep_link:
                return None
            object_id_str = deep_link.split("_")[-1]
            return await self.find_one_by_id(PydanticObjectId(object_id_str))
        except (ValueError, IndexError):
            return None

    async def count_new_customer(self, inviter: Inviter):
        inviter.invited_customers += 1
        await self.save(inviter)
    
    async def count_new_first_order(self, inviter: Inviter, order: Order, ctx: Context) -> Optional[Money]:
        inviter.invited_customers_first_orders += 1
        if inviter.inviter_type == InviterType.customer:
            customer = await self.dbs.customers.find_one_by_id(inviter.customer_id)
            if customer:
                reward = await order.price_details.get_referral_reward()
                
                return await self.dbs.customers.add_bonus_money(customer, reward, ctx)
                
        
        await self.save(inviter)
    
    async def new(self, customer_id: PydanticObjectId) -> Inviter:
        if await self.check_customer(customer_id):
            return await self.find_by_customer_id(customer_id)
        inviter = Inviter(customer_id=customer_id)
        await self.save(inviter)
        return inviter

class DeliveryRequirement(AppBaseModel):
    name: LocalizedEntry
    description: LocalizedEntry
    value: SecureValue = SecureValue() # для заполнения в будущем при конфигурации

class DeliveryRequirementsList(AppBaseModel):
    name: LocalizedEntry
    description: LocalizedEntry
    requirements: list[DeliveryRequirement]

class DeliveryService(AppDBModel):
    id: Optional[PydanticObjectId] = None
    name: LocalizedString  # Название сервиса
    is_foreign: bool = False
    requires_manual_confirmation: bool = False
    
    price: LocalizedMoney = LocalizedMoney.from_keys(RUB=500.0, USD=7.0)
    requirements_options: list[DeliveryRequirementsList] # для почты россии, например, можно оформить как по адресу с ФИО, так и просто по номеру до востребования
    selected_option: Optional[DeliveryRequirementsList] = None # для заполнения в будущем при конфигурации
    
    def index_option_by_name(self, name: LocalizedEntry) -> int:
        return next((idx for idx, option in enumerate(self.requirements_options) if option.name == name), -1)
    
    def get_selected_option_index(self):
        return self.index_option_by_name(self.selected_option.name) if self.selected_option else 0
    
    def securs_to_str(self) -> str:
        if self.selected_option is None:
            return ""
        securs = [req.value.get() for req in self.selected_option.requirements]
        
        return json.dumps(securs, ensure_ascii=False)

    def restore_securs_from_str(self, securs: str):
        if self.selected_option is None:
            return
            
        try:
            decoded_securs = json.loads(securs.encode('utf-8').decode('utf-8'))
            if not decoded_securs:
                return
                
            for req in self.selected_option.requirements:
                if decoded_securs:
                    req.value.update(decoded_securs.pop(0))
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            # Обработка ошибок декодирования или десериализации
            logging.error(f"Ошибка при восстановлении securs из строки: {e}")
            return

class DeliveryServicesRepository(AppAbstractRepository[DeliveryService]):
    class Meta:
        collection_name = 'delivery_services'
    
    async def get_all(self, is_foreign: bool) -> Iterable[DeliveryService]:
        return await self.find_by({"is_foreign": is_foreign})

class DeliveryInfo(AppBaseModel):
    
    service: Optional[DeliveryService] = None
    waiting_for_manual_delivery_info_confirmation: bool = False
    
    
    @model_validator(mode="before")
    @classmethod
    def from_v1(cls, data: dict):
        if not isinstance(data, dict):  # уже готовый объект — пропускаем
            return data
        
        if "waiting_for_manual_delivery_info_confirmation" in data:
            return data

        data['waiting_for_manual_delivery_info_confirmation'] = False

        return data
    
class PrivacyData(AppBaseModel):
    delivery_info: DeliveryInfo = Field(default_factory=DeliveryInfo)
    
    consent_process_pd: Optional[datetime] = None
    
class Customer(AppDBModel):
    schema_version: int = 1
    
    id: Optional[PydanticObjectId] = None
    user_id: int
    role: str = "default"

    invited_by: Optional[PydanticObjectId] = None
    kicked: bool = False
    banned: bool = False

    lang: str
    
    currency: str
    last_time_changed_currency: Optional[datetime] = None
    bonus_wallet: Money
    
    privacy_data: PrivacyData = Field(default_factory=PrivacyData)
    
    @model_validator(mode="before")
    @classmethod
    def migrate(cls, data: dict):
        if not isinstance(data, dict):  # уже готовый объект — пропускаем
            return data
        schema_version = data.get("schema_version", 0)
        
        
        if schema_version == 0:
            data['schema_version'] = 1

            if "delivery_info" in data and "waiting_for_manual_delivery_info_confirmation" in data:
                data['privacy_data'] = PrivacyData().model_dump()
                
                if data['delivery_info'] and data['delivery_info']['service']:
                    data['privacy_data']['delivery_info']['service'] = data.pop('delivery_info')['service']
                    
                data['privacy_data']['delivery_info']['waiting_for_manual_delivery_info_confirmation'] = data.pop('waiting_for_manual_delivery_info_confirmation')

            logging.getLogger(__name__).warning("Customer: converting from v0 to v1")
            schema_version = 1
        if schema_version == 1:
            pass
        

        return data
    
    def check_can_change_currency(self) -> bool:
        if self.last_time_changed_currency:
            if self.last_time_changed_currency.tzinfo is None:
                self.last_time_changed_currency = self.last_time_changed_currency.replace(tzinfo=timezone.utc)
            if self.last_time_changed_currency + timedelta(days=DAYS_BEFORE_CHANGE_CURRENCY) > datetime.now(timezone.utc):
                return False
        return True
    
    async def change_selected_currency(self, iso: str, ctx: Context, do_timeout: bool = True) -> None:
        """Изменить основную валюту"""
        if iso.upper() not in SUPPORTED_CURRENCIES.keys():
            raise ValueError(f"Unsupported currency: {iso}")

        self.bonus_wallet.currency = iso
        
        if self.bonus_wallet.amount > 0:
            try:
                self.bonus_wallet = Money(currency=iso, 
                                     amount=await ctx.services.currency_converter.convert(self.bonus_wallet.amount, 
                                                                                          self.currency, 
                                                                                          iso))
            except Exception as e:
                # Логируем ошибку и не меняем валюту
                logging.getLogger(__name__).critical(f"Ошибка конвертации валюты: {e}")
                raise RuntimeError(
                    "Сервис конвертации валют временно недоступен. Попробуйте позже."
                ) from e
        
        if do_timeout:
            if not self.check_can_change_currency():
                raise RuntimeError("Валюту можно менять не чаще раза в месяц!")

            self.last_time_changed_currency = datetime.now(timezone.utc)
        self.currency = iso

class CustomersRepository(AppAbstractRepository[Customer]):
    class Meta:
        collection_name = 'customers'
        
    async def new_customer(self, user_id, inviter: Inviter = None, lang: str = "?", currency: str = "RUB") -> Customer:
        customer = Customer(
                user_id=user_id,
                invited_by=inviter.id if inviter else None,
                lang=lang,
                currency=currency,
                bonus_wallet=Money(currency=currency, amount=0.0)
            )
        
        await self.save(customer)
        return customer

    async def find_by_user_id(self, user_id: int) -> Optional[Customer]:
        return await self.find_one_by({"user_id": user_id})
    
    async def find_by_users_id(self, user_ids: Iterable[int]) -> Optional[Iterable[Customer]]:
        return await self.find_by({"user_id": {"$in": user_ids}})
    
    async def find_many_by_inviter_id(self, inviter_id: PydanticObjectId) -> Optional[Iterable[Customer]]:
        return await self.find_by({"invited_by": inviter_id})
    
    async def add_bonus_money(self, customer: Customer, money: Money, ctx: Context):
        if money.amount <= 0.0001: return
        
        if money.currency != customer.currency:
            try:
                amount = await ctx.services.currency_converter.convert(money.amount, money.currency, customer.currency)
            except Exception as e:
                logging.getLogger(__name__).critical(f"Ошибка конвертации валюты: {e}")
                raise RuntimeError(
                    "Сервис конвертации валют временно недоступен. Попробуйте позже."
                ) from e
            money = Money(currency=customer.currency, amount=amount)

        customer.bonus_wallet += money
        await self.save(customer)
        return money
        
    async def remove_bonus_money(self, customer: Customer, money: Money, ctx: Context):
        if money.amount <= 0.0001: return

        if money.currency != customer.currency:
            try:
                amount = await ctx.services.currency_converter.convert(money.amount, money.currency, customer.currency)
            except Exception as e:
                logging.getLogger(__name__).critical(f"Ошибка конвертации валюты: {e}")
                raise RuntimeError(
                    "Сервис конвертации валют временно недоступен. Попробуйте позже."
                ) from e
            money = Money(currency=customer.currency, amount=amount)
            
        customer.bonus_wallet -= money
        await self.save(customer)

class Category(AppDBModel):
    id: Optional[PydanticObjectId] = None
    name: str
    localized_name: LocalizedString

class CategoriesRepository(AppAbstractRepository[Category]):
    class Meta:
        collection_name = 'categories'

    async def get_all(self) -> Optional[Iterable[Category]]:
        return await self.find_by({})

__all__ = [
    "AppAbstractRepository",
    "AppBaseModel",
    "AppDBModel",
    "LogsRepository",
    "Placeholder",
    "PlaceholdersRepository",
    "OrderPriceDetails",
    "Order",
    "OrdersRepository",
    "CartEntry",
    "CartEntriesRepository",
    "DiscountedProduct",
    "DiscountedProductsRepository",
    "ConfigurationSwitch",
    "ConfigurationSwitches",
    "ConfigurationSwitchesGroup",
    "ConfigurationChoice",
    "ConfigurationAnnotation",
    "ConfigurationOption",
    "ProductConfiguration",
    "Product",
    "ProductsRepository",
    "ProductAdditional",
    "AdditionalsRepository",
    "Promocode",
    "PromocodesRepository",
    "Inviter",
    "InvitersRepository",
    "DeliveryRequirement",
    "DeliveryRequirementsList",
    "DeliveryService",
    "DeliveryServicesRepository",
    "DeliveryInfo",
    "Customer",
    "CustomersRepository",
    "Category",
    "CategoriesRepository"
]