import logging
from os import getenv

from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.types import WebhookInfo
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from configs.environment import BASE_WEBHOOK_URL, WEBHOOK_PATH, WEBHOOK_SECRET, WEBHOOK_PATH, WEBHOOK_SECRET


async def on_startup(bot: Bot) -> None:
    url = f"{BASE_WEBHOOK_URL}{WEBHOOK_PATH}"
    
    info: WebhookInfo  = await bot.get_webhook_info()
    if info and isinstance(info, WebhookInfo) and info.url != url:
        await bot.delete_webhook(drop_pending_updates=True)
    
        await bot.set_webhook(
            url,
            secret_token=WEBHOOK_SECRET,
            drop_pending_updates=True
        )
    
    me = await bot.get_me()
    logging.getLogger(__name__).info(f"Started bot @{me.username}.")

def create_app(dp: Dispatcher, bot: Bot):
    
    dp.startup.register(on_startup)
    
    app = web.Application()

    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET,
    )
    
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)

    setup_application(app, dp, bot=bot)
    
    return app