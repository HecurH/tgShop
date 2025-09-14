import asyncio
from datetime import datetime, timedelta
import re
from typing import TYPE_CHECKING, Dict, Optional



if TYPE_CHECKING:
    from schemas.db_models import PlaceholdersRepository
    from schemas.types import LocalizedString
    from schemas.db_models import Placeholder

class PlaceholderManager:
    
    REFRESH_INTERVAL = 15 * 60 # 15m
    
    def __init__(self, repo: "PlaceholdersRepository"):
        self.repo = repo
        self._cache: dict[str, Placeholder] = {}
        
        asyncio.create_task(self._background_refresh())
    
    async def update_placeholders(self):
        placeholders = await self.repo.get_all()
        self._cache = {ph.key: ph for ph in placeholders}

    async def _background_refresh(self):
        while True:
            try:
                await self.update_placeholders()
            except Exception as e:
                print(f"Ошибка обновления кеша плейсхолдеров: {e}")
            await asyncio.sleep(self.REFRESH_INTERVAL)

    def process(self, text: str, lang: str) -> str:
        def replacer(match: re.Match) -> str:
            key = match.group(1)
            localized = self._cache.get(key).value
            
            return localized.get(lang) if localized else f"[[{key}]]"

        return re.sub(r"\[\[([a-zA-Z0-9_]+)\]\]", replacer, text)
