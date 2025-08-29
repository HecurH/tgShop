from typing import Dict, Optional
from configs.supported import SUPPORTED_CURRENCIES
from core.helper_classes import Cryptography

from pydantic import BaseModel, Field

import base64
from binascii import Error as BinasciiError

from schemas.enums import *
from ui.translates import EnumTranslates


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

    def __mul__(self, factor: float):
        return Money(currency=self.currency, amount=self.amount * factor)

    def __str__(self):
        return self.to_text()


class LocalizedMoney(BaseModel):
    data: Dict[str, Money] = Field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, float]) -> "LocalizedMoney":
        return cls(data={cur: Money(currency=cur, amount=amt) for cur, amt in raw.items()})
    
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

    def __add__(self, other):
        if not isinstance(other, LocalizedMoney):
            return NotImplemented
        result = {
            cur: self.get_amount(cur) + other.get_amount(cur)
            for cur in set(self.data) | set(other.data)
        }
        return LocalizedMoney.from_dict(result)

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
    
    def get(self, lang: str) -> str:
        return self.data.get(lang) or self.data.get("en")

class OrderState(BaseModel):
    key: OrderStateKey

    def get_localized_name(self, lang: str) -> str:
        return EnumTranslates.OrderStateKey.translate(self.key.value, lang)
    
    def set_state(self, key: OrderStateKey):
        self.key = key 
        
class Discount(BaseModel):
    action_type: DiscountType  # тип действия: фиксированная сумма или процент
    value: LocalizedMoney     # если процент — 10.0 значит 10%, если фикс — сумма в основной валюте

    def get_discount(self, amount: Money | LocalizedMoney) -> Money | LocalizedMoney:
        if isinstance(amount, LocalizedMoney):
            return LocalizedMoney(
                data={
                    cur: self.get_discount(money)
                    for cur, money in amount.data.items()
                }
            )
        
        if self.action_type == DiscountType.percent:
            discount = amount.amount * (self.value.get_amount(amount.currency) / 100)
            discount = round(min(discount, amount.amount), 2)
            return Money(currency=amount.currency, amount=max(discount, 0.0))
        elif self.action_type == DiscountType.fixed:
            discount = min(self.value.get_amount(amount.currency), amount.amount)
            discount = round(discount, 2)
            return Money(currency=amount.currency, amount=max(discount, 0.0))
        # если тип не распознан — скидка 0
        return Money(currency=amount.currency, amount=0.0)