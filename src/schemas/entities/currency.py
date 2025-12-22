from decimal import Decimal
from pydantic import BaseModel

class CurrencyInfo(BaseModel):
    iso: str
    format_template: str   # "{amount}₽", "${amount}", ...
    precision: int         # количество знаков после точки

    def quant(self) -> Decimal:
        return Decimal("1").scaleb(-self.precision)

__all__ = ["CurrencyInfo"]