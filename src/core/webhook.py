import logging
from os import getenv

from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.types import WebhookInfo
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application


def load_env(name: str) -> str:
    if value := getenv(name): return value
    else: raise KeyError(f"Missing {name} environment variable.")

async def on_startup(bot: Bot) -> None:
    url = f"{load_env('BASE_WEBHOOK_URL')}{load_env('WEBHOOK_PATH')}"
    secret_token = load_env('WEBHOOK_SECRET')
    
    info: WebhookInfo  = await bot.get_webhook_info()
    if info and isinstance(info, WebhookInfo) and info.url != url:
        await bot.delete_webhook(drop_pending_updates=False)
    
    await bot.set_webhook(
        url,
        secret_token=secret_token
    )
    
    me = await bot.get_me()
    logging.getLogger(__name__).info(f"Started bot @{me.username}")

def create_app(dp: Dispatcher, bot: Bot):
    webhook_path = load_env('WEBHOOK_PATH')
    secret_token = load_env('WEBHOOK_SECRET')
    
    dp.startup.register(on_startup)
    
    app = web.Application()

    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=secret_token,
    )
    
    webhook_requests_handler.register(app, path=webhook_path)

    setup_application(app, dp, bot=bot)
    
    return app