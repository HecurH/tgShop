from aiogram.fsm.context import FSMContext

from aiogram import Bot, Router, html, F
from aiogram.filters import CommandStart, CommandObject, Command, StateFilter
from aiogram.types import Message, LabeledPrice, PreCheckoutQuery
from aiogram.utils.formatting import as_list, Bold, BlockQuote, Text

from src.classes import keyboards
from src.classes import states

router = Router(name="commnon")



@router.message(Command("start"))
@router.message(CommandStart(deep_link=True))
async def command_start_handler(message: Message, command: CommandObject, state: FSMContext) -> None:
    await state.clear()

    await message.reply("Привет!")

    await message.answer("Вот меню:", reply_markup=keyboards.main_menu())
    await state.set_state(states.CommonStates.main_menu)

@router.message(Command("menu"))
@router.message(F.text.lower() == "меню")
async def menu_command_handler(message: Message, state: FSMContext) -> None:
    await state.clear()

    await message.answer("Вот меню:", reply_markup=keyboards.main_menu())
    await state.set_state(states.CommonStates.main_menu)


@router.message(states.CommonStates.main_menu, F.text.lower() == "о нас")
async def about_command_handler(message: Message, state: FSMContext) -> None:

    await message.reply(**as_list(
        BlockQuote(Bold("PLACEHOLDER")),
        Text("Lorem ipsum dolor sit amed.")
    ).as_kwargs(), reply_markup=keyboards.main_menu())

    await state.set_state(states.CommonStates.main_menu)


@router.message(Command("cancel"))
@router.message(F.text.lower() == "отмена")
@router.message(F.text.lower() == "назад")
async def cancel_handler(message: Message, state: FSMContext) -> None:
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

# Если нет состояния
@router.message(StateFilter(None))
async def base_handler(message: Message, state: FSMContext) -> None:
    await message.reply("Упс! Прости, мне нужно начать заново...")
    await message.answer("Вот меню:", reply_markup=keyboards.main_menu())
    await state.set_state(states.CommonStates.main_menu)