import asyncio
import base64
from datetime import datetime
import logging
import time
import os
from os import getenv
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Union

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend

from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.methods import SendMessage
import aiohttp

from MoyNalogAPI import AsyncMoyNalog
from MoyNalogAPI.schemas import Service, Client
from configs.supported import SUPPORTED_CURRENCIES
from schemas.db_models import *

from ui.message_tools import split_message
from ui.translates import TypedTranslatorHub

if TYPE_CHECKING:
    from core.db import DatabaseService
    from core.notifications import NotificatorHub
    from schemas.types import Money
    
CRYPTO_KEY = base64.b64decode(getenv("CRYPTO_KEY").encode("utf-8"))

class MessageWrapper(Message | CallbackQuery):
    
    async def answer(self, text, *args, **kwargs) -> SendMessage:
        parts = split_message(text, 4096)
        if len(parts) == 1:
            return await super().answer(text, *args, **kwargs)
        
        result_messages = []
        for i, part in enumerate(parts):
            is_last = i == len(parts) - 1
            
            if 'reply_markup' in kwargs and not is_last:
                temp_kwargs = kwargs.copy()
                temp_kwargs.pop('reply_markup', None)
                result = await super().answer(part, *args, **temp_kwargs)
            else:
                result = await super().answer(part, *args, **kwargs)
            if not is_last:
                await asyncio.sleep(0.3)
            
            result_messages.append(result)
        
        return result_messages[-1] if result_messages else None
    
    async def answer_photo(self, *args, caption = None, **kwargs):
        if caption is None:
            return await super().answer_photo(*args, **kwargs)
            
        parts = split_message(caption, 4096)
        if len(parts) == 1:
            return await super().answer_photo(*args, caption=caption, **kwargs)
        
        result_messages = []
        for i, part in enumerate(parts):
            is_first = i == 0
            is_last = i == len(parts) - 1
            if is_first:
                temp_kwargs = kwargs.copy()
                temp_kwargs.pop('reply_markup', None)
                result = await super().answer_photo(*args, caption=part, **temp_kwargs)
            elif is_last:
                result = await super().answer(part, reply_markup=kwargs.get('reply_markup', None))
            else:
                result = await super().answer(part)
                
            if not is_last:
                await asyncio.sleep(0.3)
            
            result_messages.append(result)
        
        return result_messages[-1] if result_messages else None
    
    async def answer_video(self, *args, caption = None, **kwargs):
        if caption is None:
            return await super().answer_video(*args, **kwargs)
            
        parts = split_message(caption, 4096)
        if len(parts) == 1:
            return await super().answer_video(*args, caption=caption, **kwargs)
        
        result_messages = []
        for i, part in enumerate(parts):
            is_first = i == 0
            is_last = i == len(parts) - 1
            if is_first:
                temp_kwargs = kwargs.copy()
                temp_kwargs.pop('reply_markup', None)
                result = await super().answer_video(*args, caption=part, **temp_kwargs)
            elif is_last:
                result = await super().answer(part, reply_markup=kwargs.get('reply_markup', None))
            else:
                result = await super().answer(part)
                
            if not is_last:
                await asyncio.sleep(0.3)
            
            result_messages.append(result)
        
        return result_messages[-1] if result_messages else None

@dataclass
class Context:
    event: Union[Message, CallbackQuery]
    fsm: FSMContext
    db: "DatabaseService"
    customer: "Customer"
    lang: str
    t: TypedTranslatorHub
    tax: "TaxSystem"
    n: "NotificatorHub"

    @property
    def message(self) -> Message:
        attr = getattr(self.event, "message", self.event)
        return MessageWrapper(attr)
        
    
    async def parse_user_input(self, text: Optional[str] = None):
        if text is None: text = self.message.text
        if not text: return None
        
        if len(text) > 1024:
            await self.message.answer(self.t.UncategorizedTranslates.input_message_too_long)
            return None

        return text

    async def get_last_bot_message(self) -> Optional[Message]:
        last_bot_message = await self.fsm.get_value("last_bot_message")
        
        if last_bot_message: return Message(**last_bot_message).as_(self.event.bot)
    
    async def get_last_bot_message(self) -> Optional[Message]:
        last_bot_message = await self.fsm.get_value("last_bot_message")
        
        if last_bot_message: return Message(**last_bot_message).as_(self.event.bot)
    
    async def set_last_bot_message(self, msg: Message):
        await self.fsm.update_data(last_bot_message=msg.model_dump())

    @property
    def is_query(self) -> bool:
        return isinstance(self.event, CallbackQuery)

class Cryptography:
    
    @staticmethod
    def encrypt_data(data: str) -> tuple[bytes, bytes, bytes]:
        """Шифрование данных с использованием AES-256-GCM."""
        # Генерация случайного вектора инициализации (IV)
        iv = os.urandom(12)
        # Создание шифра
        cipher = Cipher(algorithms.AES(CRYPTO_KEY), modes.GCM(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        # Шифрование данных + добавление padding
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(data.encode()) + padder.finalize()
        ciphertext = encryptor.update(padded_data) + encryptor.finalize()
        return iv, ciphertext, encryptor.tag

    @staticmethod
    def decrypt_data(iv: bytes, ciphertext: bytes, tag: bytes) -> str:
        """Дешифрование данных."""
        cipher = Cipher(algorithms.AES(CRYPTO_KEY), modes.GCM(iv, tag), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted_data = decryptor.update(ciphertext) + decryptor.finalize()
        # Удаление padding
        unpadder = padding.PKCS7(128).unpadder()
        unpadded_data = unpadder.update(decrypted_data) + unpadder.finalize()
        return unpadded_data.decode()

# класс для учета налогов в системе
class TaxSystem:
    def __init__(self, config_path: str = "/src/configs/"):
        self.client = AsyncMoyNalog(config_path)
        
    async def safe_create_invoice(self, *args, retries: int = 3, timeout: int = 10, **kwargs):
        last_exc = None
        for attempt in range(retries):
            try:
                return await asyncio.wait_for(
                    self.client.create_invoice(*args, **kwargs),
                    timeout=timeout
                )
            except (asyncio.TimeoutError, Exception) as e:
                last_exc = e
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)  # экспоненциальная задержка
                    continue
                raise last_exc
        
    def distribute_discounts(self, cart_entries: list["CartEntry"], total_discount: "Money") -> list["Money"]:
        from schemas.types import LocalizedMoney, Money
        entry_prices = [
            (entry.configuration.price + entry.frozen_product.base_price) * entry.quantity
            for entry in cart_entries
        ]
        
        total_price = sum(entry_prices, LocalizedMoney())
        
        if total_price.get_amount(total_discount.currency) == 0:
            return [Money(currency=total_discount.currency, amount=0.0) for _ in cart_entries]
        
        discounts = []
        remaining_discount = total_discount.amount
        
        for price in entry_prices[:-1]:
            fraction = price.get_amount(total_discount.currency) / total_price.get_amount(total_discount.currency)
            discount_amount = fraction * total_discount.amount
            discount_amount = min(discount_amount, price.get_amount(total_discount.currency))
            discount_amount = round(discount_amount, 2)
            discounts.append(Money(currency=total_discount.currency, amount=discount_amount))
            remaining_discount -= discount_amount
        
        last_discount = min(remaining_discount, entry_prices[-1].get_amount(total_discount.currency))
        last_discount = round(last_discount, 2)
        discounts.append(Money(currency=total_discount.currency, amount=last_discount))
        
        return discounts

    async def invoice_by_order(self, cart_entries: list["CartEntry"], order: "Order", operation_time: datetime) -> str | list[str]:
        from schemas.types import Money
        price_details = order.price_details
        
        services = []
        client_data = Client()
        
        discounts = (price_details.bonuses_applied or Money(currency=price_details.products_price.currency, amount=0.0)) + (price_details.promocode_discount or Money(currency=price_details.products_price.currency, amount=0.0))
        entry_discounts = self.distribute_discounts(cart_entries, discounts)
        
        entries_list = [
            [
                f"ТЕСТОВЫЙ {entry.frozen_product.name_for_tax}",
                (entry.configuration.price.get_amount(discounts.currency) + entry.frozen_product.base_price.get_amount(discounts.currency)) * entry.quantity - entry_discounts[i].amount,
                entry.quantity
            ] 
            for i, entry in enumerate(cart_entries)
        ]

        for name, price, quantity in entries_list:
            if price > 0.001: services.append(Service(name=name, amount=price, quantity=quantity))
            
        if len(services) == 0: return None
        if len(services) > 6:
            chunks = [services[i:i + 6] for i in range(0, len(services), 6)]
            receipts = []
            for services_chunk in chunks:
                
                receipts.append(await self.safe_create_invoice(
                    operation_time=operation_time,
                    svs=services_chunk,
                    client=client_data,
                    payment_type="WIRE",
                    return_receipt_url=True
                ))
            return receipts
            
        return await self.safe_create_invoice(
            operation_time=operation_time,
            svs=services,
            client=client_data,
            payment_type="WIRE",
            return_receipt_url=True
        )
        

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

        # self.init_session()
        
    def init_session(self):
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
        self.init_session()

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