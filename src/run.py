import asyncio
import logging
import re
import shutil
import sys
from os import getenv
from colorlog import ColoredFormatter

from aiogram import Bot, Dispatcher, F
from aiogram.fsm.storage.pymongo import PyMongoStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from pathlib import Path

from pymongo import AsyncMongoClient

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from handlers import admin_menu, discounted_products, profile, admin, bottom, cart, orders, common, assortment
from core import middlewares

def load_env(name: str) -> str:
    if value := getenv(name): return value
    else: raise KeyError(f"Missing {name} environment variable.")

BOT_TOKEN = load_env("BOT_TOKEN")
MONGO_URI = load_env("MONGO_URI")
MONGO_TLS_CA_PATH = load_env("MONGO_TLS_CA_PATH")

dp = Dispatcher(storage=PyMongoStorage(AsyncMongoClient(MONGO_URI, 
                                                        tls=True, 
                                                        tlsAllowInvalidCertificates=True, 
                                                        tlsCAFile=MONGO_TLS_CA_PATH)))

dp.message.filter(F.chat.type == "private")
dp.update.middleware.register(middlewares.ThrottlingMiddleware())
context_middleware = middlewares.ContextMiddleware()
dp.update.middleware.register(context_middleware)

LOG_LEVEL = logging.INFO
LOGFORMAT = "%(log_color)s%(levelname)-8s%(reset)s | %(log_color)s%(message)s%(reset)s // %(name)s - %(funcName)s: %(lineno)d | %(asctime)s"



class _BaseAlignedFormatter:
    log_tail_width = 40

    def _strip_colors(self, text):
        return re.sub(r'\x1B[@-_][0-?]*[ -/]*[@-~]', '', text)

    def _align(self, base_message, record):
        tail = f"// {record.name} - {record.funcName}: {record.lineno} | {record.asctime}"
        if tail in base_message:
            base_message = base_message.replace(tail, "").rstrip()
        try:
            total_width = shutil.get_terminal_size()[0]
        except Exception:
            total_width = 120
        visible_len = len(self._strip_colors(base_message))
        space_left = max(1, total_width - visible_len - len(tail))
        return base_message + " " * space_left + tail


class AlignedColorFormatter(_BaseAlignedFormatter, ColoredFormatter):
    def format(self, record):
        base_message = super().format(record)
        return self._align(base_message, record)


class AlignedPlainFormatter(_BaseAlignedFormatter, logging.Formatter):
    def __init__(self, fmt, datefmt=None):
        # убираем цветовые теги
        fmt = fmt.replace("%(log_color)s", "").replace("%(reset)s", "")
        super().__init__(fmt, datefmt=datefmt)

    def format(self, record):
        base_message = super().format(record)
        return self._align(base_message, record)

formatter_color = AlignedColorFormatter(LOGFORMAT, datefmt="%m-%d %H:%M:%S")
formatter_plain = AlignedPlainFormatter(LOGFORMAT, datefmt="%m-%d %H:%M:%S")


stream = logging.StreamHandler()
stream.setFormatter(formatter_color)

from logging.handlers import TimedRotatingFileHandler

logs_dir = Path("/gss_logs/")
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
file_handler.setFormatter(formatter_plain)

logging.basicConfig(level=LOG_LEVEL, handlers=[stream, file_handler])
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("aiogram.event").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def main() -> None:
    bot = Bot(token=BOT_TOKEN,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML)
              )

    dp.include_routers(common.router,
                       admin.router,
                       admin_menu.router,
                       assortment.router,
                       discounted_products.router,
                       cart.router,
                       orders.router,
                       profile.router,
                       bottom.router)
    
    dp.workflow_data["context_middleware"] = context_middleware
    dp.workflow_data["bot"] = bot

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())