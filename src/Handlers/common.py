import asyncio
import logging
import shutil
import sys
from os import getenv
from colorlog import ColoredFormatter

from aiogram import Bot, Router, html, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.types import Message, LabeledPrice, PreCheckoutQuery

router = Router(name="commnon")


@router.message(Command("suka"))
async def command_start_handler(message: Message, command: CommandObject) -> None:
    """
    This handler receives messages with `/start` command
    """
    # Most event objects have aliases for API methods that can be called in events' context
    # For example if you want to answer to incoming message you can use `message.answer(...)` alias
    # and the target chat will be passed to :ref:`aiogram.methods.send_message.SendMessage`
    # method automatically or call API method directly via
    # Bot instance: `bot.send_message(chat_id=message.chat.id, ...)`
    await message.answer_invoice("Плоти денге",
                                 "описалса",
                                 "idхуйди",
                                 currency="rub",
                                 prices=[
                                     LabeledPrice(label="RUB", amount=1000)
                                 ],
                                 provider_token="1744374395:TEST:2c5a6f30c2763af47ad6")

@router.pre_checkout_query()
async def on_pre_checkout_query(
    pre_checkout_query: PreCheckoutQuery,
):
    await pre_checkout_query.answer(ok=True)

@router.message(F.successful_payment)
async def on_successful_payment(
    message: Message,
):
    await message.answer(
        "YAY",
        # Это эффект "огонь" из стандартных реакций
        message_effect_id="5104841245755180586"
    )