from typing import Optional
from pydantic import BaseModel

from schemas.types import LocalizedString


class PaymentMethod(BaseModel):
    name: LocalizedString
    description: LocalizedString
    enabled: bool = True
    
    can_register_receipts: bool = True
    
    manual: bool

class PaymentMethodsRepository:
    def __init__(self, methods: dict[str, PaymentMethod]):
        self.data = methods
    
    def get_enabled(self) -> list[PaymentMethod]:
        return [method for method in self.data if method.enabled]
    
    def get_by_key(self, key) -> Optional[PaymentMethod]:
        return self.data.get(key)