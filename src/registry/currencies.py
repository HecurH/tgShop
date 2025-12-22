from typing import Dict
from schemas.entities.currency import CurrencyInfo


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

__all__ = ["SUPPORTED_CURRENCIES"]