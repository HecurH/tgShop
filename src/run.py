import logging
import sys
from os import getenv

from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.fsm.storage.pymongo import PyMongoStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from pathlib import Path

from pymongo import AsyncMongoClient

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from handlers import admin_menu, discounted_products, profile, admin, bottom, cart, orders, common, assortment
from core.logger import setup_logging
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
dp.update.middleware.register(middlewares.ErrorLoggingMiddleware())

setup_logging()
logger = logging.getLogger(__name__)


def main() -> None:
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
    
    if getenv("USE_WEBHOOK") == "1":
        from core.webhook import create_app
    
        app = create_app(dp, bot)
        
        web.run_app(app, 
                    host=load_env('WEB_SERVER_HOST'), 
                    port=int(load_env('WEB_SERVER_PORT')),
                    access_log=None,
                    print=None)
    else:
        import asyncio
        
        async def polling():
            await bot.delete_webhook(drop_pending_updates=False)
            await dp.start_polling(bot)
        
        asyncio.run(polling())


if __name__ == "__main__":
    main()