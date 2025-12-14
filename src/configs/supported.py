
from decimal import Decimal
from typing import Dict

from pydantic import BaseModel

class CurrencyInfo(BaseModel):
    iso: str
    format_template: str   # "{amount}₽", "${amount}", ...
    precision: int         # количество знаков после точки

    def quant(self) -> Decimal:
        return Decimal("1").scaleb(-self.precision)

SUPPORTED_CURRENCIES: Dict[str, CurrencyInfo] = {
    "RUB": CurrencyInfo(
        iso="RUB",
        format_template="{amount}₽",
        precision=2
    ),
    "USD": CurrencyInfo(
        iso="USD",
        format_template="${amount}",
        precision=2
    )
}

SUPPORTED_LANGUAGES_TEXT = {
    "🇷🇺Русский": "ru",
    "🇺🇸English": "en"
}

DAYS_BEFORE_CHANGE_CURRENCY = 30