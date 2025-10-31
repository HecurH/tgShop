import logging
from typing import TYPE_CHECKING, Dict, Optional, Union
from configs.supported import SUPPORTED_CURRENCIES
from core.helper_classes import Context, Cryptography

from aiogram.types import Message
from pydantic import BaseModel, Field

import base64
from binascii import Error as BinasciiError

from schemas.enums import *
from ui.translates import EnumTranslates

if TYPE_CHECKING:
    from core.services.placeholders import PlaceholderManager


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
    currency: str  # ISO
    amount: float
    
    def to_text(self) -> str:
        sign = "-" if self.amount < 0 else ""
        template = SUPPORTED_CURRENCIES.get(self.currency, f"{{amount}}{self.currency}")
        
        num = round(abs(self.amount), 2)
        amount = template.format(amount=f"{int(num)}" if num == int(num) else f"{num:.2f}")
        return f"{sign}{amount}"

    def __add__(self, other):
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {self.currency} != {other.currency}")
        return Money(currency=self.currency, amount=self.amount + other.amount)
    
    def __sub__(self, other):
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {self.currency} != {other.currency}")
        return Money(currency=self.currency, amount=self.amount - other.amount)

    
    def __lt__(self, other):
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {self.currency} != {other.currency}")
        return self.amount < other.amount

    def __le__(self, other):
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {self.currency} != {other.currency}")
        return self.amount <= other.amount

    def __eq__(self, other):
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {self.currency} != {other.currency}")
        return self.amount == other.amount


    def __mul__(self, factor: float):
        return Money(currency=self.currency, amount=self.amount * factor)

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
    
    def get_amount(self, cur: str) -> float:
        return self.data.get(cur, Money(currency=cur, amount=0.0)).amount

    def get_money(self, cur: str) -> Money:
        return self.data.get(cur, Money(currency=cur, amount=0.0))
    
    def set_amount(self, curency: str, amount: float):
        self.data[curency] = Money(currency=curency, amount=amount)

    def to_text(self, currency: str) -> str:
        if money := self.data.get(currency):
            return str(money)
        
        template = SUPPORTED_CURRENCIES.get(currency, f"{{amount}}{currency}")
        return template.format(amount=0)
    
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

    def __mul__(self, factor: float) -> "LocalizedMoney":
        return LocalizedMoney(
            data={cur: money * factor for cur, money in self.data.items()}
        )

    def __imul__(self, factor: float) -> "LocalizedMoney":
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
                current_obj = "Could not find localized attribute {attr}"
                
        
        return current_obj

class SavedTMessage(BaseModel):
    chat_id: int
    message_id: int

class LocalizedSavedMedia(BaseModel):
    media_type: MediaType
    media_id: Union[dict[str, str], str]
    
    @classmethod
    def from_keys(cls, media_type: MediaType, **kwargs):
        return cls(media_type=media_type, media_id={key: kwargs[key] for key in kwargs})
    
    def get(self, lang: str) -> str:
        if isinstance(self.media_id, str): return self.media_id
        return self.media_id.get(lang, self.media_ids.get("en"))


class MediaPlaceholderLink(BaseModel):
    placeholder_key: str
    
    async def resolve(self, ctx: Context) -> Optional[str]:
        return ctx.services.placeholders.resolve_media(self.placeholder_key)

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
    value: LocalizedMoney | float     # если процент — 10.0 значит 10%, если фикс — сумма в основной валюте

    def get_discount(self, amount: Money | LocalizedMoney) -> Money | LocalizedMoney:
        if isinstance(amount, LocalizedMoney):
            return LocalizedMoney(
                data={
                    cur: self.get_discount(money)
                    for cur, money in amount.data.items()
                }
            )
        
        if self.dicount_type == DiscountType.percent:
            discount = amount.amount * (self.value / 100)
            discount = round(min(discount, amount.amount), 2)
            return Money(currency=amount.currency, amount=max(discount, 0.0))
        elif self.dicount_type == DiscountType.fixed:
            discount = min(self.value.get_amount(amount.currency), amount.amount)
            discount = round(discount, 2)
            return Money(currency=amount.currency, amount=max(discount, 0.0))
        # если тип не распознан — скидка 0
        return Money(currency=amount.currency, amount=0.0)


__all__ = ["SecureValue", "Money", "LocalizedMoney", "LocalizedString", "LocalizedEntry", "LocalizedSavedMedia", "MediaPlaceholderLink", "OrderState", "Discount", "SavedTMessage"]