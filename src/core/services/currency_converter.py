import traceback
from configs.supported import SUPPORTED_CURRENCIES
import aiohttp

import asyncio
import logging


class AsyncCurrencyConverter:
    """
    Асинхронный конвертер валют с фоновым обновлением кэша.
    Инициализирует ресурсы и запускает фоновую задачу при создании экземпляра.
    """

    BASE_API = "https://api.exchangerate-api.com/v4/latest/"
    REFRESH_TIME = 1800  # 30 минут

    def __init__(self):
        self._logger = logging.getLogger(__name__)
        
        self._session = aiohttp.ClientSession()
        self._refresh_task = asyncio.create_task(self._background_refresh_task())
        
        self._cache: dict = {}
        self._initial_update_done = asyncio.Event()
        self._logger.info("Converter initialized, session and background task created.")
        

    async def close(self):
        self._logger.info("Closing converter resources...")
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass  # Ожидаемое исключение при отмене задачи
            self._logger.info("Background refresh task cancelled.")

        if self._session and not self._session.closed:
            await self._session.close()
            self._logger.info("aiohttp session closed.")

    async def _background_refresh_task(self):
        """Бесконечный цикл для периодического обновления кэша в фоне."""
        self._logger.info("Background refresh task started.")
        while True:
            try:
                await self.update_all_rates()
                self._initial_update_done.set()
                self._logger.debug(f"Rates updated. Next update in {self.REFRESH_TIME} seconds.")
            except Exception as e:
                self._logger.error(f"Failed to update currency rates in background: {e}")
                if not self._initial_update_done.is_set() and not self._cache:
                    self._logger.critical("Initial cache update failed. Converter is non-operational.")
            await asyncio.sleep(self.REFRESH_TIME)

    async def update_all_rates(self):
        """Обновляет кэшированные курсы для всех поддерживаемых валют."""
        tasks = [self._fetch_rate(currency) for currency in SUPPORTED_CURRENCIES.keys()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_rates = {}
        for currency, result in zip(SUPPORTED_CURRENCIES.keys(), results):
            if isinstance(result, Exception):
                raise result 
            all_rates[currency] = result
        
        self._cache = all_rates
        self._logger.debug("Currency rates cache has been successfully updated.")

    async def _fetch_rate(self, currency: str) -> dict:
        """Вспомогательный метод для получения курса одной валюты."""
        url = f"{self.BASE_API}{currency}"
        try:
            async with self._session.get(url, timeout=10) as response:
                response.raise_for_status()
                data = await response.json()
                if "rates" not in data:
                    raise ValueError(f"No 'rates' in API response for {currency}")
                return data["rates"]
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            self._logger.error(f"Error fetching rates for {currency}: {e}")
            raise RuntimeError(f"Could not fetch rates for {currency}") from e

    async def _get_all_rates(self) -> dict:
        """Возвращает кэш, дождавшись его первого заполнения."""
        await self._initial_update_done.wait()
        return self._cache

    async def convert(self, amount: float, from_currency: str, to_currency: str) -> float:
        """Преобразует сумму из одной валюты в другую."""
        if amount < 0:
            raise ValueError("Amount must be non-negative")

        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        all_rates = await self._get_all_rates()
        if not all_rates:
             raise RuntimeError("Currency rates are not available. Check background task errors.")

        rates_from = all_rates.get(from_currency)
        if rates_from is None:
            raise ValueError(f"Currency {from_currency} is not supported")

        rate_to = rates_from.get(to_currency)
        if rate_to is None:
            raise ValueError(f"Currency {to_currency} is not supported")
            
        return amount * rate_to