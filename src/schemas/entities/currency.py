from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CurrencyInfo:
    iso: str
    format_template: str   # "{amount}₽", "${amount}", ...
    precision: int         # количество знаков после точки

    def quant(self) -> Decimal:
        return Decimal("1").scaleb(-self.precision)

__all__ = ["CurrencyInfo"]