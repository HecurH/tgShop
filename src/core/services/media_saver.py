import asyncio
import json
import os
from os.path import join, splitext, relpath
from os import getenv
from typing import Optional, Union

from aiogram import Bot
from aiogram.types import BufferedInputFile

from configs.supported import SUPPORTED_LANGUAGES_TEXT
from schemas.enums import MediaType


class MediaSaver:
    
    REFRESH_INTERVAL = 15 * 60  # 15m
    
    def __init__(self, media_path: str = None, bot: Bot = None):
        self.media_path = media_path or getenv("MEDIA_PATH")
        if not self.media_path:
            raise RuntimeError("Не задан MEDIA_PATH")
        
        self.bot = bot
        
        admin_chat_id = getenv("TG_ADMIN_CHAT_ID")
        if not admin_chat_id:
            raise RuntimeError("Не задан TG_ADMIN_CHAT_ID")
        self.admin_chat_id = int(admin_chat_id)
        
        self.supported_langs = set(SUPPORTED_LANGUAGES_TEXT.values())
        self._media_cache: dict[str, Union[str, dict[str, str]]] = {}
        
        asyncio.create_task(self._background_refresh())
    
    async def update_cache(self):
        data_path = join(self.media_path, "data.json")

        if not os.path.exists(data_path):
            with open(data_path, "w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=2)

        with open(data_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}

        # Ищем все файлы рекурсивно
        all_files = []
        for root, _, files in os.walk(self.media_path):
            for f in files:
                if f == "data.json":
                    continue
                all_files.append(join(root, f))

        updated = False

        for filepath in all_files:
            rel_file = relpath(filepath, self.media_path)  # путь относительно корня
            filename = os.path.basename(filepath)
            key_base, _ = splitext(filename)
            lang = key_base.split("_")[-1]
            if lang in self.supported_langs:
                key = key_base.replace(f"_{lang}", "")
            else:
                key = key_base
                lang = None

            if key not in data:
                if lang:
                    data[key] = {lang: await self._generate_id_for_file(key, filepath)}
                else:
                    data[key] = await self._generate_id_for_file(key, filepath)
                updated = True
                    
            if lang and lang not in data[key]:
                data[key][lang] = await self._generate_id_for_file(key, filepath)
                updated = True

        # чистим отсутствующие файлы
        existing_keys = set()
        for filepath in all_files:
            filename = os.path.basename(filepath)
            key_base, _ = splitext(filename)
            lang = key_base.split("_")[-1]
            key = key_base.replace(f"_{lang}", "") if lang in self.supported_langs else key_base
            existing_keys.add(key)

        removed_keys = [k for k in list(data.keys()) if k not in existing_keys]
        if removed_keys:
            for k in removed_keys:
                del data[k]
                updated = True

        self._media_cache = data

        if updated:
            with open(data_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    
    async def _generate_id_for_file(self, key: str, filepath: str) -> str:
        media_type = self.media_type_by_key(key)
        with open(filepath, "rb") as f:
            file_bytes = f.read()
            
        await asyncio.sleep(5)
        
        try:

            if media_type == MediaType.photo:
                msg = await self.bot.send_photo(
                    chat_id=self.admin_chat_id,
                    photo=BufferedInputFile(file_bytes, filename=os.path.basename(filepath))
                )
                await msg.delete()
                return msg.photo[-1].file_id
            elif media_type == MediaType.video:
                msg = await self.bot.send_video(
                    chat_id=self.admin_chat_id,
                    video=BufferedInputFile(file_bytes, filename=os.path.basename(filepath))
                )
                await msg.delete()
                return msg.video.file_id
            elif media_type == MediaType.document:
                msg = await self.bot.send_document(
                    chat_id=self.admin_chat_id,
                    document=BufferedInputFile(file_bytes, filename=os.path.basename(filepath))
                )
                await msg.delete()
                return msg.document.file_id
            else:
                raise ValueError(f"Неизвестный тип медиа: {media_type}")
            
        except Exception as e:
            raise RuntimeError(f"Ошибка при загрузке файла {filepath}: {e}")

    async def _background_refresh(self):
        while True:
            try:
                await self.update_cache()
            except Exception as e:
                print(f"Ошибка обновления кеша медиа: {e}")
            await asyncio.sleep(self.REFRESH_INTERVAL)
    
    def media_type_by_key(self, key: str) -> Optional[MediaType]:
        if key.startswith("photo"): return MediaType.photo
        elif key.startswith("video"): return MediaType.video
        elif key.startswith("document"): return MediaType.document
        else: return None
    
    def resolve_key(self, key: str) -> Optional[tuple[MediaType, Union[str, dict[str, str]]]]:
        file_data = self._media_cache.get(key)
        if not file_data:
            return None

        media_type = self.media_type_by_key(key)
        return media_type, file_data
