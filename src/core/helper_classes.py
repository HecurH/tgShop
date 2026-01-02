import asyncio
import base64
import os
from os import getenv
from dataclasses import dataclass
import string
from typing import TYPE_CHECKING, Optional, Union

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend

from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
import re

from schemas.db_models import *

from ui.message_tools import split_message
from ui.translates import TypedTranslatorHub

if TYPE_CHECKING:
    from core.services.db import DatabaseService
    from core.services.notifications import NotificatorHub
    from core.services.tax import TaxSystem
    from core.services.placeholders import PlaceholderManager
    from core.services.currency_converter import AsyncCurrencyConverter
    from core.services.media_saver import MediaSaver
    
CRYPTO_KEY = base64.b64decode(getenv("CRYPTO_KEY").encode("utf-8"))

class MessageWrapper:
    def __init__(self, message: Message, ctx: "Context"):
        self._message = message
        self._ctx = ctx
        
    async def delete(self, *args, **kwargs):
        try:
            await self._message.delete()
            return True
        except Exception:
            return False
        
    async def answer(self, text, *args, **kwargs):
        parts = split_message(text, 4096)
        if len(parts) == 1:
            return await self._message.answer(text, *args, **kwargs)
        
        result_messages = []
        for i, part in enumerate(parts):
            is_last = i == len(parts) - 1
            
            if 'reply_markup' in kwargs and not is_last:
                temp_kwargs = kwargs.copy()
                temp_kwargs.pop('reply_markup', None)
                result = await self._message.answer(part, *args, **temp_kwargs)
            else:
                result = await self._message.answer(part, *args, **kwargs)
            if not is_last:
                await asyncio.sleep(0.4)
            
            await self._ctx.update_messages_log(result)
            result_messages.append(result)
        
        return result_messages[-1] if result_messages else None
    
    async def answer_photo(self, *args, caption = None, **kwargs):
        if caption is None:
            return await self._message.answer_photo(*args, **kwargs)
            
        parts = split_message(caption, 4096)
        if len(parts) == 1:
            if len(caption) > 1024:
                temp_kwargs = kwargs.copy()
                temp_kwargs.pop('reply_markup', None)
                await self._message.answer_photo(*args, **temp_kwargs)
                
                return await self._message.answer(caption, reply_markup=kwargs.get('reply_markup', None))
            
            return await self._message.answer_photo(*args, caption=caption, **kwargs)
        
        result_messages = []
        for i, part in enumerate(parts):
            is_first = i == 0
            is_last = i == len(parts) - 1
            if is_first:
                temp_kwargs = kwargs.copy()
                temp_kwargs.pop('reply_markup', None)
                await self._message.answer_photo(*args, **temp_kwargs)
                result = await self._message.answer(part, reply_markup=kwargs.get('reply_markup', None))
            elif is_last:
                result = await self._message.answer(part, reply_markup=kwargs.get('reply_markup', None))
            else:
                result = await self._message.answer(part)
                
            if not is_last:
                await asyncio.sleep(0.4)
            
            result_messages.append(result)
        
        return result_messages[-1] if result_messages else None
    
    async def answer_video(self, *args, caption = None, **kwargs):
        if caption is None:
            return await self._message.answer_video(*args, **kwargs)
            
        parts = split_message(caption, 4096)
        if len(parts) == 1:
            if len(caption) > 1024:
                temp_kwargs = kwargs.copy()
                temp_kwargs.pop('reply_markup', None)
                await self._message.answer_video(*args, **temp_kwargs)
                
                return await self._message.answer(caption, reply_markup=kwargs.get('reply_markup', None))
            
            return await self._message.answer_video(*args, caption=caption, **kwargs)
        
        result_messages = []
        for i, part in enumerate(parts):
            is_first = i == 0
            is_last = i == len(parts) - 1
            if is_first:
                temp_kwargs = kwargs.copy()
                temp_kwargs.pop('reply_markup', None)
                
                await self._message.answer_video(*args, **temp_kwargs)
                result = await self._message.answer(part, reply_markup=kwargs.get('reply_markup', None))
            elif is_last:
                result = await self._message.answer(part, reply_markup=kwargs.get('reply_markup', None))
            else:
                result = await self._message.answer(part)
                
            if not is_last:
                await asyncio.sleep(0.4)
            
            result_messages.append(result)
        
        return result_messages[-1] if result_messages else None
    
    def __getattr__(self, item):
        return getattr(self._message, item)

@dataclass
class ServiceHub:
    db: "DatabaseService"
    tax: "TaxSystem"
    notificators: "NotificatorHub"
    placeholders: "PlaceholderManager"
    currency_converter: "AsyncCurrencyConverter"
    media_saver: "MediaSaver"

@dataclass
class Context:
    event: Union[Message, CallbackQuery]
    fsm: FSMContext
    customer: "Customer"
    lang: str
    t: TypedTranslatorHub
    
    services: ServiceHub

    @property
    def message(self) -> Message:
        attr: Message = getattr(self.event, "message", self.event)
        return MessageWrapper(attr, self)
        
    
    async def parse_user_input(self, text: Optional[str] = None):
        if text is None: text = self.message.text
        if not text: return None
        
        # Разрешаем:
        # \p{L} — все буквы (включая славянские, латинские, польские и т.д.)
        # \p{N} — цифры
        # \p{P} — пунктуация
        # \p{S} — символы (валюты, мат. знаки, спец. символы)
        # \p{M} — диакритические знаки (акценты и т.п.).
        allowed = (
            r"[^"
            r"\w"                     # буквы + цифры + _
            r"\s"                     # пробелы
            + re.escape(string.punctuation) +  # стандартные знаки препинания
            r"№€£¥§±×÷°•–—…„“”«»"     # вручную добавленные часто используемые спецсимволы
            r"]+"
        )
        
        text = re.sub(allowed, "", text, flags=re.UNICODE)
        
        if len(text) > 1024:
            await self.message.answer(self.t.UncategorizedTranslates.input_message_too_long)
            return None

        return text
    
    async def update_messages_log(self, message: Message):
        messages_log: list[int] = await self.fsm.get_value("messages_log") or []
        def push(buf, x, limit=30):
            buf.append(x)
            if len(buf) > limit:
                del buf[0]
                
        push(messages_log, message.message_id)

        await self.fsm.update_data(messages_log=messages_log)
    
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

