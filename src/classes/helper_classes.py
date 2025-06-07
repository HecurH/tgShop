import asyncio
import time
import logging
from dataclasses import dataclass
from typing import Union, TYPE_CHECKING

from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
import aiohttp

from src.classes.config import SUPPORTED_CURRENCIES
from src.classes.db_models import *

if TYPE_CHECKING:
    from db import DB

@dataclass
class Context:
    event: Union[Message, CallbackQuery]
    fsm: FSMContext
    db: "DB"
    customer: "Customer"
    lang: str

    @property
    def message(self) -> Message:
        return getattr(self.event, "message", self.event)


class ProductConfigEditor:
    def __init__(self, product: Product):
        self.product = product

    def get_option_by_label(self, label: str, lang: str) -> tuple[str, ConfigurationOption]:
        for key, option in self.product.configuration.options.items():
            if option.name.data[lang] == label:
                return key, option
        raise ValueError(f"Option with label '{label}' not found")
    
    def get_choice_by_label(self, option: ConfigurationOption, label: str, lang: str):
        for choice in option.choices:
            if hasattr(choice, "label") and choice.label.data[lang] == label:
                return choice
        raise ValueError(f"Choice with label '{label}' not found in option '{option.name.data[lang]}'")

    def get_choice_index_by_label(self, option: ConfigurationOption, label: str, lang: str) -> int:
        for i, choice in enumerate(option.choices):
            if hasattr(choice, "label") and choice.label.data[lang] == label:
                return i
        raise ValueError(f"Choice with label '{label}' not found in option '{option.name.data[lang]}'")

    def update_switches(self, option_key: str, switches: ConfigurationSwitches, lang: str):
        option = self.product.configuration.options[option_key]
        idx = self.get_choice_index_by_label(option, switches.label.data[lang], lang)
        option.choices[idx] = switches
        self.product.configuration.options[option_key] = option
    
    def update_option(self, option_key: str, option: ConfigurationOption):
        self.product.configuration.options[option_key] = option
        
    def dump(self):
        return self.product.model_dump()

class AsyncCurrencyConverter:
    """Асинхронный конвертер валют с кэшированием и обновлением курсов.

    Класс предоставляет методы для конвертации сумм между поддерживаемыми валютами с использованием актуальных курсов.
    Управляет собственной сессией aiohttp и кэширует курсы для минимизации количества запросов к API.
    """
    
    BASE_API = "https://api.exchangerate-api.com/v4/latest/"
    REFRESH_TIME = 1800  # 30 минут

    def __init__(self):
        self._session = None  # Одна сессия для всех запросов
        self._cache: dict = {}  # {валюта: курсы}
        self._last_update: float = 0
        self._lock = asyncio.Lock()  # Одна блокировка для всего кэша
        
        self._logger = logging.getLogger(__name__)
        
    async def init_session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._logger.debug("CurrencyConverter aiohttp session created.")

    async def close(self):
        if self._session is not None:
            await self._session.close()
            self._session = None
            self._logger.debug("CurrencyConverter aiohttp session closed.")
        
    async def update_all_rates(self):
        """Обновляет кэшированные курсы для всех поддерживаемых валют.

        Метод получает актуальные курсы валют с внешнего API и сохраняет их в кэше для последующего использования.

        Raises:
            RuntimeError: Если возникает ошибка при получении или обработке данных от API.
            Exception: Для неожиданных ошибок во время обновления курсов.
        """
        await self.init_session()

        all_rates = {}
        for currency in SUPPORTED_CURRENCIES.keys():
            url = f"{self.BASE_API}{currency}"
            try:
                async with self._session.get(url, timeout=10) as response:
                    if response.status != 200:
                        self._logger.error(f"API error: HTTP {response.status} for {currency}")
                        raise RuntimeError(f"API error: HTTP {response.status}")
                    try:
                        data = await response.json()
                    except Exception as e:
                        self._logger.error(f"JSON decode error for {currency}: {e}")
                        raise RuntimeError(f"JSON decode error for {currency}: {e}") from e
                    if "rates" not in data:
                        self._logger.error(f"No 'rates' in API response for {currency}: {data}")
                        raise RuntimeError(f"No 'rates' in API response for {currency}")
                    all_rates[currency] = data["rates"]
            except asyncio.TimeoutError as exc:
                self._logger.error(f"Timeout while fetching rates for {currency}")
                raise RuntimeError(f"Timeout while fetching rates for {currency}") from exc
            except aiohttp.ClientError as e:
                self._logger.error(f"Network error while fetching rates for {currency}: {e}")
                raise RuntimeError(
                    f"Network error while fetching rates for {currency}: {e}"
                ) from e
            except Exception as e:
                self._logger.error(f"Unexpected error while fetching rates for {currency}: {e}")
                raise

        self._cache = all_rates
        self._last_update = time.time()

        self._logger.debug("Currency rates updated.")

    async def _get_all_rates(self) -> dict:
        """Получить курсы валют для всех поддерживаемых валют."""
        now = time.time()
        all_rates = self._cache

        if now - self._last_update < self.REFRESH_TIME and all_rates:
            return all_rates

        async with self._lock:
            # Повторная проверка кэша после ожидания блокировки
            all_rates = self._cache
            if time.time() - self._last_update < self.REFRESH_TIME and all_rates:
                return all_rates

            try:
                await self.update_all_rates()
            except Exception as e:
                self._logger.error(f"Failed to update currency rates: {e}")
                # Можно пробросить ошибку дальше, либо вернуть старый кэш, если он есть
                if self._cache:
                    self._logger.warning("Returning cached rates due to update failure.")
                    return self._cache
                raise

            return self._cache

    async def convert(self, amount: float, from_currency: str, to_currency: str) -> float:
        """Преобразует сумму из одной валюты в другую с использованием актуальных курсов.

        Метод получает актуальные курсы и выполняет конвертацию между поддерживаемыми валютами.

        Args:
            amount: Сумма для конвертации. Должна быть неотрицательной.
            from_currency: Код валюты, из которой конвертируется сумма (например, 'USD').
            to_currency: Код валюты, в которую конвертируется сумма (например, 'RUB').

        Returns:
            Конвертированная сумма в виде числа с плавающей точкой.

        Raises:
            ValueError: Если сумма отрицательная или одна из валют не поддерживается.
            Exception: Для неожиданных ошибок во время конвертации.
        """
        try:
            if amount < 0:
                raise ValueError("Amount must be non-negative")

            from_currency = from_currency.upper()
            to_currency = to_currency.upper()

            all_rates = await self._get_all_rates()
            if from_currency not in all_rates:
                self._logger.error(f"Currency {from_currency} not supported")
                raise ValueError(f"Currency {from_currency} not supported")
            rates = all_rates[from_currency]
            if to_currency not in rates:
                self._logger.error(f"Currency {to_currency} not supported")
                raise ValueError(f"Currency {to_currency} not supported")

            return amount * rates[to_currency]
        except Exception as e:
            self._logger.error(f"Error in convert: {e}")
            raise