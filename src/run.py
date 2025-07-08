import asyncio
import logging
import shutil
import sys
from os import getenv
from colorlog import ColoredFormatter

from aiogram import Bot, Dispatcher, F
from aiogram.fsm.storage.mongo import MongoStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path

from src.handlers import profile

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from handlers import admin, bottom, common, assortment
from classes import middlewares

# Bot token can be obtained via https://t.me/BotFather
TOKEN = getenv("BOT_TOKEN")

# All handlers should be attached to the Router (or Dispatcher)

dp = Dispatcher(storage=MongoStorage(AsyncIOMotorClient(getenv("MONGO_URI"))))

dp.message.filter(F.chat.type == "private")
dp.update.middleware.register(middlewares.ThrottlingMiddleware())
dp.update.middleware.register(middlewares.ContextMiddleware())

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

from logging.handlers import TimedRotatingFileHandler

logs_dir = Path("logs")
logs_dir.mkdir(exist_ok=True)

# TimedRotatingFileHandler будет создавать новый файл каждый день
file_handler = TimedRotatingFileHandler(
    filename=logs_dir / "current.log",
    when="midnight",
    interval=1,
    backupCount=30,
    encoding="utf-8",
    utc=False
)

# Переопределяем метод namer, чтобы архивные логи были вида "18_06_25.log"
def custom_namer(default_name):
    # default_name: logs/current.log.2024-06-25_00-00-00
    import re
    if match := re.search(r'(\d{4}-\d{2}-\d{2})', default_name):
        y, m, d = match.group(1).split('-')
        short_name = f"{y[2:]}_{m}_{d}.log"
        return str(logs_dir / short_name)
    return default_name

file_handler.namer = custom_namer

logging.basicConfig(level=LOG_LEVEL, handlers=[stream, file_handler])
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("aiogram.event").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def main() -> None:
    # Initialize Bot instance with default bot properties which will be passed to all API calls
    bot = Bot(token=TOKEN,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML)
              )

    dp.include_routers(admin.router,
                       common.router,
                       assortment.router,
                       profile.router,
                       bottom.router)

    # And the run events dispatching
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())