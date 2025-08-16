from typing import Dict, Optional
from enum import Enum
from configs.supported import SUPPORTED_CURRENCIES
from core.helper_classes import Cryptography

from pydantic import BaseModel

import base64

from schemas.enums import *
from ui.translates import EnumTranslates


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

class Money(BaseModel):
    currency: str  # ISO
    amount: float
    
    def to_text(self) -> str:
        template = SUPPORTED_CURRENCIES.get(self.currency, f"{{amount}}{self.currency}")
        amount = round(self.amount, 2)
        return template.format(
            amount=f"{int(amount)}" if amount == int(amount) else f"{amount:.2f}"
        )

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
    data: Dict[str, Money] = {}

    @classmethod
    def from_dict(cls, raw: dict[str, float]) -> "LocalizedMoney":
        return cls(data={cur: Money(currency=cur, amount=amt) for cur, amt in raw.items()})
    
    def get_amount(self, cur: str) -> float:
        return self.data.get(cur, Money(currency=cur, amount=0.0)).amount

    def get_money(self, cur: str) -> Money:
        return self.data.get(cur, Money(currency=cur, amount=0.0))
    
    def set_amount(self, cur: str, amount: float):
        self.data[cur] = Money(cur, amount)

    def to_text(self, currency: str) -> str:
        if money := self.data.get(currency):
            return str(money)
        
        template = SUPPORTED_CURRENCIES.get(self.currency, f"{{amount}}{self.currency}")
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
            return LocalizedMoney.from_dict(self.data.copy())
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
        return EnumTranslates.OrderState.translate(self.key.value, lang)
    
    def set_state(self, key: OrderStateKey):
        self.key = key 
        
class PromocodeAction(BaseModel):
    action_type: PromocodeActionType  # тип действия: фиксированная сумма или процент
    value: LocalizedMoney     # если процент — 10.0 значит 10%, если фикс — сумма в основной валюте

    def get_discount(self, amount: Money) -> Money:
        # округляем результат до двух знаков после запятой
        if self.action_type == PromocodeActionType.percent:
            discount_amount = round(amount.amount * (self.value.get_amount(amount.currency) / 100), 2)
            return Money(currency=amount.currency, amount=discount_amount)
        elif self.action_type == PromocodeActionType.fixed:
            discount = min(self.value.get_amount(amount.currency), amount.amount)
            discount = round(discount, 2)
            return Money(currency=amount.currency, amount=discount)
        # если тип не распознан — скидка 0
        return Money(currency=amount.currency, amount=0.0)