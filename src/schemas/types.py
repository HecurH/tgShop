from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from bson import Decimal128
from typing import TYPE_CHECKING, Any, Dict, Optional, Union
from configs.supported import SUPPORTED_CURRENCIES
from core.helper_classes import Context, Cryptography

from aiogram.types import Message
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_core import core_schema

import base64
from binascii import Error as BinasciiError

from schemas.enums import *
from ui.translates import EnumTranslates

if TYPE_CHECKING:
    from core.services.placeholders import PlaceholderManager
class DecimalAnnotation:
    
    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: Any
    ) -> core_schema.CoreSchema:
        """Схема для валидации и сериализации Decimal полей."""
        
        def validate_to_decimal(value: Any) -> Decimal:
            """Конвертируем различные типы в Decimal."""
            if isinstance(value, Decimal):
                return value
            elif isinstance(value, Decimal128):
                return value.to_decimal()
            elif isinstance(value, str):
                try:
                    return Decimal(value)
                except InvalidOperation as e:
                    raise ValueError(f"Invalid decimal string: {value}") from e
            elif isinstance(value, (int, float)):
                # Для float есть потеря точности, но это ожидаемо
                return Decimal(str(value))
            else:
                raise ValueError(f"Cannot convert {type(value).__name__} to Decimal")
        
        # Схема для валидации входящих данных в Decimal
        decimal_schema = core_schema.no_info_plain_validator_function(validate_to_decimal)
        
        # Сериализатор для конвертации Decimal -> Decimal128 при дампе в словарь
        def serialize_to_decimal128(value: Decimal, _info) -> Decimal128:
            """Сериализуем Decimal в Decimal128 для Python dict."""
            return Decimal128(str(value))
        
        # Схема для конвертации Decimal -> строка при дампе в JSON
        def serialize_to_string(value: Decimal, _info) -> str:
            """Сериализуем Decimal в строку для JSON."""
            return str(value)
        
        return core_schema.json_or_python_schema(
            json_schema=core_schema.str_schema(),
            python_schema=core_schema.union_schema(
                [
                    core_schema.is_instance_schema(Decimal),
                    core_schema.is_instance_schema(Decimal128),
                    decimal_schema,
                ]
            ),
            # Двойная сериализация: для JSON и для Python dict
            serialization=core_schema.plain_serializer_function_ser_schema(
                function=lambda value, info=None: (
                    serialize_to_string(value, info) if info and info.mode == 'json'
                    else serialize_to_decimal128(value, info)
                ),
                return_schema=core_schema.union_schema([
                    core_schema.str_schema(),
                    core_schema.is_instance_schema(Decimal128),
                ]),
                when_used='always',
            ),
        )


class SecureValue(BaseModel):
    iv: str = ""
    ciphertext: str = ""
    tag: str = ""

    def get(self) -> Optional[str]:
        """Дешифрует и возвращает строковое значение, обрабатывая ошибки base64 декодирования."""
        if not self.iv or not self.ciphertext or not self.tag:
            return None

        try:
            iv_bytes = base64.b64decode(self.iv, validate=True)
            ciphertext_bytes = base64.b64decode(self.ciphertext, validate=True)
            tag_bytes = base64.b64decode(self.tag, validate=True)
        except BinasciiError:
            print("Error: Invalid base64 characters found during decoding.")
            return None
        except ValueError as e:
            print(f"Error: A ValueError occurred during base64 decoding. Details: {e}")
            return None
        
        return Cryptography.decrypt_data(
            iv_bytes,
            ciphertext_bytes,
            tag_bytes
        )

    def update(self, text: str):
        """Шифрует строку и сохраняет результат в поля."""
        iv, ciphertext, tag = Cryptography.encrypt_data(text)
        self.iv = base64.b64encode(iv).decode()
        self.ciphertext = base64.b64encode(ciphertext).decode()
        self.tag = base64.b64encode(tag).decode()

class Money(BaseModel):
    currency: str
    amount: DecimalAnnotation
    
    @field_validator("amount", mode="before")
    def convert_decimal(cls, v):
        return Decimal(str(v))

    @field_validator("currency")
    def check_currency(cls, v):
        if v not in SUPPORTED_CURRENCIES:
            raise ValueError(f"Unsupported currency: {v}")
        return v
    
    @model_validator(mode="after")
    def normalize(self):
        self.amount = self._quantize(self.amount)
        return self
    
    
    def to_text(self) -> str:
        info = SUPPORTED_CURRENCIES[self.currency]
        
        sign = "-" if self.amount < 0 else ""
        abs_amount = abs(self.amount)
        
        rounded = abs_amount.quantize(info.quant(), rounding=ROUND_HALF_UP)
        
        if rounded == rounded.to_integral():
            amount_text = f"{rounded.to_integral()}"
        else:
            fmt = f"{{0:.{info.precision}f}}"
            amount_text = fmt.format(rounded)
        
        formatted = info.format_template.format(amount=amount_text)
        return f"{sign}{formatted}"
    
    def _quantize(self, value: Decimal) -> Decimal:
        info = SUPPORTED_CURRENCIES[self.currency]
        return value.quantize(info.quant(), rounding=ROUND_HALF_UP)
    
    def _check(self, other):
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {self.currency} != {other.currency}")
        return SUPPORTED_CURRENCIES[self.currency]

    def __add__(self, other: "Money"):
        self._check(other)
        return Money(currency=self.currency, amount=self.amount + other.amount)
    
    def __sub__(self, other: "Money"):
        self._check(other)
        return Money(currency=self.currency, amount=self.amount - other.amount)
    
    def __lt__(self, other: "Money"):
        self._check(other)
        return self.amount < other.amount

    def __le__(self, other: "Money"):
        self._check(other)
        return self.amount <= other.amount

    def __eq__(self, other: object):
        self._check(other)
        return self.amount == other.amount

    def __mul__(self, factor):
        val = self._quantize(self.amount * Decimal(str(factor)))
        return Money(currency=self.currency, amount=val)
    
    def __truediv__(self, factor):
        val = self._quantize(self.amount / Decimal(str(factor)))
        return Money(currency=self.currency, amount=val)

    def __str__(self):
        return self.to_text()

class LocalizedMoney(BaseModel):
    data: Dict[str, Money] = Field(default_factory=dict)
    
    @classmethod
    def from_keys(cls, **kwargs):
        return cls(data={cur: Money(currency=cur, amount=kwargs[cur]) for cur in kwargs})
    
    @classmethod
    def empty_base(cls) -> "LocalizedMoney":
        return cls(data={cur: Money(currency=cur, amount=0.0) for cur in SUPPORTED_CURRENCIES})
    
    def get_amount(self, cur: str) -> Decimal:
        return self.data.get(cur, Money(currency=cur, amount=0.0)).amount

    def get_money(self, cur: str) -> Money:
        return self.data.get(cur, Money(currency=cur, amount=0.0))
    
    def set_amount(self, curency: str, amount: Decimal):
        self.data[curency] = Money(currency=curency, amount=amount)

    def to_text(self, currency: str) -> str:
        if money := self.data.get(currency): return money.to_text()
        return Money(currency=currency, amount=0.0).to_text()
    
    def to_text_all(self) -> str:
        return ", ".join(self.to_text(cur) for cur in self.data)

    def __add__(self, other):
        if not isinstance(other, LocalizedMoney):
            return NotImplemented
        result = {
            cur: self.get_amount(cur) + other.get_amount(cur)
            for cur in set(self.data) | set(other.data)
        }
        return LocalizedMoney.from_keys(**result)

    def __sub__(self, other):
        if not isinstance(other, LocalizedMoney):
            return NotImplemented
        result = {
            cur: self.get_amount(cur) - other.get_amount(cur)
            for cur in set(self.data) | set(other.data)
        }
        return LocalizedMoney.from_keys(**result)

    def __iadd__(self, other: "LocalizedMoney") -> "LocalizedMoney":
        for cur, money in other.data.items():
            self.data[cur] = self.data[cur] + money if cur in self.data else money
        return self

    def __radd__(self, other):
        if other == 0:
            return LocalizedMoney(data=self.data.copy())
        return self.__add__(other)

    def __mul__(self, factor) -> "LocalizedMoney":
        return LocalizedMoney(
            data={cur: money * factor for cur, money in self.data.items()}
        )

    def __imul__(self, factor) -> "LocalizedMoney":
        for cur in self.data:
            self.data[cur] = self.data[cur] * factor
        return self

class LocalizedString(BaseModel):
    data: dict[str, str]
    
    @classmethod
    def from_keys(cls, **kwargs):
        return cls(data={key: kwargs[key] for key in kwargs})
    
    def raw(self, lang: str) -> str: return self.data.get(lang) or self.data.get("en")
    
    def get(self, lang_or_context: str | Context, pm: "PlaceholderManager" = None) -> str:
        if isinstance(lang_or_context, Context): return lang_or_context.services.placeholders.process_text(self.raw(lang_or_context.lang), lang_or_context.lang)
        
        raw = self.raw(lang_or_context)
        if pm is not None:
            return pm.process_text(raw, lang_or_context)
        return raw
    
class LocalizedEntry(BaseModel):
    """Класс для хранения динамических и распространненых данных в БД"""
    path: str
    
    def get(self, ctx: Context) -> str:
        current_obj = ctx.t.DBEntryTranslates
        for attr in self.path.split("."):
            if hasattr(current_obj, attr):
                current_obj = getattr(current_obj, attr)
            else:
                current_obj = f"Could not find localized attribute {attr}"
                
        
        return current_obj

class SavedTMessage(BaseModel):
    chat_id: int
    message_id: int

class LocalizedSavedMedia(BaseModel):
    media_key: str
    
    @classmethod
    def from_keys(cls, **kwargs):
        return cls(media_id={key: kwargs[key] for key in kwargs})
    
    def get(self, ctx: Context) -> tuple[MediaType | None, str | None]:
        media_type, media_id = ctx.services.media_saver.resolve_key(self.media_key) or (None, None)
        if media_id is None: return None, None
        
        if isinstance(media_id, dict): return media_type, media_id.get(ctx.lang)
        return media_type, media_id

class OrderState(BaseModel):
    key: OrderStateKey
    comment: list["SavedTMessage"] = Field(default_factory=list)

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
    
        
class Discount(BaseModel):
    dicount_type: DiscountType  # тип действия: фиксированная сумма или процент
    value: LocalizedMoney | DecimalAnnotation     # если процент — 10.0 значит 10%, если фикс — сумма в основной валюте
    
    @field_validator("value", mode="before")
    def convert_decimal(cls, v):
        return v if isinstance(v, LocalizedMoney) or isinstance(v, Decimal) else Decimal(str(v))

    def get_discount(self, amount: Money | LocalizedMoney) -> Money | LocalizedMoney:
        if isinstance(amount, LocalizedMoney):
            return LocalizedMoney(
                data={
                    cur: self.get_discount(money)
                    for cur, money in amount.data.items()
                }
            )
        
        if self.dicount_type == DiscountType.percent:
            discount = amount.amount * (self.value / Decimal("100"))
            discount = min(discount, amount.amount)
            return Money(currency=amount.currency, amount=max(discount, Decimal("0")))
        elif self.dicount_type == DiscountType.fixed:
            discount = min(self.value.get_amount(amount.currency), amount.amount)
            return Money(currency=amount.currency, amount=max(discount, Decimal("0")))
        # если тип не распознан — скидка 0
        return Money(currency=amount.currency, amount=Decimal("0"))


__all__ = ["SecureValue", "Money", "LocalizedMoney", "LocalizedString", "LocalizedEntry", "LocalizedSavedMedia", "OrderState", "Discount", "SavedTMessage"]