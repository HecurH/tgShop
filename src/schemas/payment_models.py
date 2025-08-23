from typing import Optional
from pydantic import BaseModel

from schemas.types import LocalizedString


class PaymentMethod(BaseModel):
    name: LocalizedString
    description: LocalizedString
    payment_details: LocalizedString # реквизиты для оплаты типо
    enabled: bool = True
    
    can_register_receipts: bool = True
    
    manual: bool

class PaymentMethodsRepository:
    def __init__(self, methods: dict[str, PaymentMethod]):
        self.data = methods
    
    def get_enabled(self) -> dict[str, PaymentMethod]:
        return {key: method for key, method in self.data.items() if method.enabled}
    
    def get_by_key(self, key) -> Optional[PaymentMethod]:
        return self.data.get(key)
    
    def get_by_name(self, name, ctx, only_enabled=False) -> Optional[tuple[str, PaymentMethod]]:
        return next(((key, method) for key, method in self.data.items() if method.name.get(ctx.lang) == name and (not only_enabled or method.enabled)), None)