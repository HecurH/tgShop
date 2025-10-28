import asyncio
import re
from typing import TYPE_CHECKING, Optional



if TYPE_CHECKING:
    from schemas.db_models import PlaceholdersRepository, MediaPlaceholdersRepository
    from schemas.types import LocalizedSavedMedia
    from schemas.db_models import Placeholder

class PlaceholderManager:
    
    REFRESH_INTERVAL = 15 * 60 # 15m
    
    def __init__(self, txt_repo: "PlaceholdersRepository", media_repo: "MediaPlaceholdersRepository"):
        self.txt_repo = txt_repo
        self.media_repo = media_repo
        
        self._txt_cache: dict[str, "Placeholder"] = {}
        self._media_cache: dict[str, "LocalizedSavedMedia"] = {}
        
        asyncio.create_task(self._background_refresh())
    
    async def update_placeholders(self):
        txt_placeholders = await self.txt_repo.get_all()
        media_placeholders = await self.media_repo.get_all()
        
        self._txt_cache = {ph.key: ph for ph in txt_placeholders}
        self._media_cache = {ph.key: ph.value for ph in media_placeholders}

    async def _background_refresh(self):
        while True:
            try:
                await self.update_placeholders()
            except Exception as e:
                print(f"Ошибка обновления кеша плейсхолдеров: {e}")
            await asyncio.sleep(self.REFRESH_INTERVAL)

    def process_text(self, text: str, lang: str) -> str:
        def replacer(match: re.Match) -> str:
            key = match.group(1)
            localized = self._txt_cache.get(key).value
            
            return localized.get(lang) if localized else f"[[{key}]]"

        return re.sub(r"\[\[([a-zA-Z0-9_]+)\]\]", replacer, text)
    
    def resolve_media(self, key: str) -> Optional["LocalizedSavedMedia"]:
        return self._media_cache.get(key)
