from aiogram.fsm.context import FSMContext

from aiogram import Bot, Router, html, F
from aiogram.filters import CommandStart, CommandObject, Command, StateFilter, ChatMemberUpdatedFilter, MEMBER, KICKED
from aiogram.types import Message, LabeledPrice, PreCheckoutQuery, CallbackQuery, InlineKeyboardMarkup, \
    ReplyKeyboardRemove, ChatMemberUpdated
from aiogram.utils.formatting import as_list, Bold, BlockQuote, Text
from pyanaconda.core.async_utils import async_action_wait

from src.classes import keyboards
from src.classes.db import *
from src.classes.middlewares import MongoDBMiddleware
from src.classes.states import CommonStates
from src.classes.translates import CommonTranslates, UncategorizedTranslates

router = Router(name="commnon")



@router.message(Command("start"))
@router.message(CommandStart(deep_link=True))
async def command_start_handler(message: Message, command: CommandObject, state: FSMContext, db: DB, lang: str) -> None:
    await state.clear()

    user = await db.customers.get_user_by_id(message.from_user.id)
    if not user:
        inviter = await db.get_one_by_query(Inviter, {"inviter_code": command.args}) if command.args else None

        await db.insert(
            Customer(
                user_id=message.from_user.id,
                invited_by=inviter.inviter_code if inviter else "",
                lang="?"
            )
        )
    if lang == "?":


        await message.answer("Выберите язык:\n\nChoose language:", reply_markup=keyboards.lang_choose())
        await state.set_state(CommonStates.lang_choosing)
        return

    await message.reply(CommonTranslates.translate("hi", lang))

    await message.answer(CommonTranslates.translate("heres_the_menu", lang), reply_markup=keyboards.main_menu(lang))
    await state.set_state(CommonStates.main_menu)


@router.callback_query(CommonStates.lang_choosing)
async def lang_changing_handler(callback: CallbackQuery, state: FSMContext, db: DB, lang: str, middleware: MongoDBMiddleware) -> None:
    user = await db.customers.get_user_by_id(callback.from_user.id)
    user.lang = callback.data

    await db.update(user)

    await callback.message.delete()
    await callback.message.answer(CommonTranslates.translate("heres_the_menu", lang), reply_markup=keyboards.main_menu(user.lang))
    await state.set_state(CommonStates.main_menu)

    await callback.answer()




# @router.message(Command("menu"))
# @router.message(F.text.lower() == CommonTranslates.menu[user.lang])
# @router.message(F.text.lower() == "меню")
# async def menu_command_handler(message: Message, state: FSMContext, db: DB) -> None:
#     await state.clear()
#
#     await message.answer(CommonTranslates.heres_the_menu, reply_markup=keyboards.main_menu())
#     await state.set_state(CommonStates.main_menu)


@router.message(CommonStates.main_menu, lambda message: message.text.lower() in CommonTranslates.about_menu.values())
async def about_command_handler(message: Message, state: FSMContext, lang: str) -> None:

    await message.reply(**as_list(
        BlockQuote(Bold("PLACEHOLDER")),
        Text("Lorem ipsum dolor sit amed.")
    ).as_kwargs(), reply_markup=keyboards.main_menu(lang))

    await state.set_state(CommonStates.main_menu)


# @router.message(Command("cancel"))
# @router.message(F.text.lower() == "отмена")
# @router.message(F.text.lower() == "назад")
# async def cancel_handler(message: Message, state: FSMContext) -> None:
#     await state.clear()
#
#
#
#     await message.answer_invoice("Плоти денге",
#                                  "описалса",
#                                  "idхуйди",
#                                  currency="rub",
#                                  prices=[
#                                      LabeledPrice(label="Базовая цена", amount=10000),
#                                      LabeledPrice(label="скидка", amount=-1000)
#                                  ],
#                                  provider_token="1744374395:TEST:2c5a6f30c2763af47ad6",
#                                  need_shipping_address=True,
#                                  )

# Если нет состояния
@router.message(StateFilter(None))
async def base_handler(message: Message, state: FSMContext, db, lang):
    await state.clear()
    #await message.reply(UncategorizedTranslates.oopsie[lang if lang != "?" else "ru"], reply_markup=ReplyKeyboardRemove())

    await command_start_handler(message, CommandObject(), state, db, lang)

@router.callback_query()
async def base_callback_handler(callback: CallbackQuery, state: FSMContext, db: DB, lang: str, middleware: MongoDBMiddleware) -> None:
    await callback.answer()

@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED))
async def user_blocked_bot(event: ChatMemberUpdated, state: FSMContext, db: DB):
    await state.clear()

    user = await db.customers.get_user_by_id(event.from_user.id)
    user.kicked = True
    await db.update(user)


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def user_unblocked_bot(event: ChatMemberUpdated, state: FSMContext, db: DB):
    await state.clear()

    user = await db.customers.get_user_by_id(event.from_user.id)
    user.kicked = False
    await db.update(user)