import asyncio
import logging
import shutil
from os import getenv
from colorlog import ColoredFormatter

from aiogram import Bot, Dispatcher, F
from aiogram.fsm.storage.mongo import MongoStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from motor.motor_asyncio import AsyncIOMotorClient

from handlers import common, shopping
from classes import middlewares

# Bot token can be obtained via https://t.me/BotFather
TOKEN = getenv("BOT_TOKEN")

# All handlers should be attached to the Router (or Dispatcher)

dp = Dispatcher(storage=MongoStorage(AsyncIOMotorClient()))
dp.message.filter(F.chat.type == "private")
dp.update.middleware.register(middlewares.MongoDBMiddleware())

LOG_LEVEL = logging.INFO
LOGFORMAT = "%(log_color)s%(levelname)-8s%(reset)s | %(log_color)s%(message)s%(reset)s // %(name)s - %(funcName)s: %(lineno)d | %(asctime)s"


class AlignedFormatter(ColoredFormatter):
    def __init__(self, fmt=None, datefmt=None, style='%', log_tail_width=40):
        super().__init__(fmt, datefmt, style)
        self.log_tail_width = log_tail_width  # ширина правой части (хвоста)


    def format(self, record):
        base_message = super().format(record)

        # Строим "хвост" — это будет правая часть
        tail = f"// {record.name} - {record.funcName}: {record.lineno} | {record.asctime}"

        # Удаляем хвост из base_message, чтобы добавить пробелы
        if tail in base_message:
            base_message = base_message.replace(tail, "").rstrip()

        # Рассчитываем отступ между основным текстом и хвостом
        total_width = shutil.get_terminal_size()[0]  # ширина всей строки (можно подогнать под ширину терминала)
        space_left = total_width - len(self._strip_colors(base_message)) - len(tail)
        space_left = max(1, space_left)

        return base_message + " " * space_left + tail


    def _strip_colors(self, text):
        import re
        ansi_escape = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')
        return ansi_escape.sub('', text)


formatter = AlignedFormatter(LOGFORMAT, datefmt="%m-%d %H:%M:%S")
stream = logging.StreamHandler()
stream.setFormatter(formatter)

logging.basicConfig(level=LOG_LEVEL, handlers=[stream])
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("aiogram.event").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)



async def main() -> None:
    # Initialize Bot instance with default bot properties which will be passed to all API calls
    bot = Bot(token=TOKEN,
              #default=DefaultBotProperties(parse_mode=ParseMode.HTML)
              )

    dp.include_routers(shopping.router, common.router)

    # And the run events dispatching
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())