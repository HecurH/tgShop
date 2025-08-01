from typing import Dict, Optional
from configs.supported import SUPPORTED_CURRENCIES
from core.helper_classes import Cryptography

from pydantic import BaseModel

import base64


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

    def __add__(self, other):
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {self.currency} != {other.currency}")
        return Money(currency=self.currency, amount=self.amount + other.amount)

    def __mul__(self, factor: float):
        return Money(currency=self.currency, amount=self.amount * factor)

    def __str__(self):
        symbol = SUPPORTED_CURRENCIES.get(self.currency, self.currency)
        return f"{self.amount:.2f}{symbol}"


class LocalizedMoney(BaseModel):
    data: Dict[str, Money] = {}

    @classmethod
    def from_dict(cls, raw: dict[str, float]) -> "LocalizedMoney":
        return cls(data={cur: Money(currency=cur, amount=amt) for cur, amt in raw.items()})

    def to_text(self, currency: str) -> str:
        if money := self.data.get(currency):
            return str(money)
        else:
            return f"0.00{SUPPORTED_CURRENCIES.get(currency, currency)}"

    def __add__(self, other: "LocalizedMoney") -> "LocalizedMoney":
        result = self.data.copy()
        for cur, money in other.data.items():
            result[cur] = result[cur] + money if cur in result else money
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
