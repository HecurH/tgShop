from aiogram.fsm.context import FSMContext

from aiogram import Router
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.formatting import as_list, Bold, BlockQuote, Text

from src.classes.db import *
from src.classes.keyboards import CommonKBs, AssortmentKBs
from src.classes.middlewares import MongoDBMiddleware
from src.classes.states import CommonStates, MainMenuOptions
from src.classes.translates import CommonTranslates, AssortmentTranslates, \
    ReplyButtonsTranslates

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


        await message.answer("Выберите язык:\n\nChoose language:", reply_markup=CommonKBs.lang_choose())
        await state.set_state(CommonStates.lang_choosing)
        return

    await message.reply(CommonTranslates.translate("hi", lang))

    await message.answer(CommonTranslates.translate("heres_the_menu", lang), reply_markup=CommonKBs.main_menu(lang))
    await state.set_state(CommonStates.main_menu)


@router.callback_query(CommonStates.lang_choosing)
async def lang_changing_handler(callback: CallbackQuery, state: FSMContext, db: DB, lang: str, middleware: MongoDBMiddleware) -> None:
    user = await db.customers.get_user_by_id(callback.from_user.id)
    user.lang = callback.data

    await db.update(user)

    await callback.message.delete()
    await callback.message.answer(CommonTranslates.translate("heres_the_menu", callback.data), reply_markup=CommonKBs.main_menu(user.lang))
    await state.set_state(CommonStates.main_menu)

    await callback.answer()


@router.message(CommonStates.main_menu, lambda message: (message.text.lower() in CommonTranslates.about_menu.values()) if message.text else False)
async def about_command_handler(message: Message, state: FSMContext, lang: str) -> None:

    await message.reply(**as_list(
        BlockQuote(Bold("PLACEHOLDER")),
        Text("Lorem ipsum dolor sit amed.")
    ).as_kwargs(), reply_markup=CommonKBs.main_menu(lang))

    await state.set_state(CommonStates.main_menu)

@router.message(CommonStates.main_menu, lambda message: (message.text in ReplyButtonsTranslates.assortment.values()) if message.text else False)
async def assortment_command_handler(message: Message, state: FSMContext, db: DB, lang: str) -> None:
    await message.answer(AssortmentTranslates.translate("choose_the_category", lang),
                         reply_markup=await AssortmentKBs.assortment_menu(db, lang))
    await state.set_state(MainMenuOptions.Assortment)

@router.message(CommonStates.main_menu)
async def bad_menu_handler(message: Message, state: FSMContext, lang: str) -> None:

    await message.answer(CommonTranslates.translate("heres_the_menu", lang),
                                  reply_markup=CommonKBs.main_menu(lang))

