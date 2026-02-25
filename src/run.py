import logging
import sys
from os import getenv

import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.fsm.storage.pymongo import PyMongoStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from pathlib import Path

from pymongo import AsyncMongoClient

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))
sys.path.insert(0, str(Path(__file__).parent))   # adds src/ directory

from handlers import admin_menu, discounted_products, profile, admin, bottom, cart, orders, common, assortment
from core.logger import setup_logging
from core import middlewares
from configs.environment import BOT_TOKEN, MONGO_URI, MONGO_TLS_CA_PATH, MONGO_TLS_KEY_PATH, USE_WEBHOOK, APP_SERVER, WEB_SERVER_HOST, WEB_SERVER_PORT


async def main():

    dp = Dispatcher(storage=PyMongoStorage(AsyncMongoClient(MONGO_URI, 
                    tls=True, 
                    tlsCAFile=MONGO_TLS_CA_PATH,
                    tlsCertificateKeyFile=MONGO_TLS_KEY_PATH)))

    
    dp.update.middleware.register(middlewares.ThrottlingMiddleware())
    context_middleware = middlewares.ContextMiddleware()
    dp.update.middleware.register(context_middleware)
    dp.update.middleware.register(middlewares.ErrorLoggingMiddleware())

    setup_logging()
    
    
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
    
    if USE_WEBHOOK:
        from core.webhook import create_app
        app = create_app(dp, bot)
        
        app_server = APP_SERVER
        if app_server == "gunicorn":
            return app
        else:
            from aiohttp import web
            await web._run_app(app, 
                        host=WEB_SERVER_HOST, 
                        port=WEB_SERVER_PORT,
                        access_log=None,
                        print=None)
    else:
        
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())