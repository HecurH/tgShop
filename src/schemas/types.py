from typing import Optional
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


class LocalizedString(BaseModel):
    data: dict[str, str]
    
    def get(self, lang: str) -> str:
        return self.data.get(lang) or self.data.get("en")
    
class PaymentMethod(BaseModel):
    name: LocalizedString
    description: LocalizedString
    can_register_receipts: bool = True
    
    manual: bool