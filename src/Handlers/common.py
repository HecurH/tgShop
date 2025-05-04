from aiogram.fsm.context import FSMContext

from aiogram import Bot, Router, html, F
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.types import Message, LabeledPrice, PreCheckoutQuery

from src.classes import keyboards

router = Router(name="commnon")



@router.message(CommandStart(deep_link=True))
async def command_start_handler(message: Message, command: CommandObject, state: FSMContext) -> None:
    await state.clear()

    await message.reply("Привет!")
    await message.answer("Вот меню:", reply_markup=keyboards.main_menu())

@router.message(Command("cancel"))
@router.message(F.text.lower == "отмена")
async def cancel_handler(message: Message, command: CommandObject, state: FSMContext) -> None:
    await state.clear()



    # await message.answer_invoice("Плоти денге",
    #                              "описалса",
    #                              "idхуйди",
    #                              currency="rub",
    #                              prices=[
    #                                  LabeledPrice(label="Базовая цена", amount=10000),
    #                                  LabeledPrice(label="скидка", amount=-1000)
    #                              ],
    #                              provider_token="1744374395:TEST:2c5a6f30c2763af47ad6")

