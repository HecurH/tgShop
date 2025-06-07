from aiogram.fsm.context import FSMContext

from aiogram import Router
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.formatting import as_list, Bold, BlockQuote, Text

from src.classes.db import *
from src.classes.helper_classes import Context
from src.classes.keyboards import CommonKBs, AssortmentKBs
from src.classes.middlewares import ContextMiddleware
from src.classes.states import CommonStates, MainMenuOptions, call_state_handler
from src.classes.translates import CommonTranslates, AssortmentTranslates, \
    ReplyButtonsTranslates

router = Router(name="common")



@router.message(Command("start"))
@router.message(CommandStart(deep_link=True))
async def command_start_handler(message: Message, ctx: Context, command: CommandObject) -> None:
    await ctx.fsm.clear()

    user = await ctx.db.customers.get_customer_by_id(message.from_user.id)
    if not user:
        inviter = await ctx.db.get_one_by_query(Inviter, {"inviter_code": command.args}) if command.args else None

        await ctx.db.insert(
            Customer(
                user_id=message.from_user.id,
                invited_by=inviter.inviter_code if inviter else "",
                lang="?"
            )
        )
    if ctx.lang == "?":
        await call_state_handler(CommonStates.lang_choosing, 
                           ctx)
        return
    await message.reply(CommonTranslates.translate("hi", ctx.lang))

    await call_state_handler(CommonStates.main_menu, 
                       ctx)

@router.callback_query(CommonStates.lang_choosing)
async def lang_changing_handler(callback: CallbackQuery, ctx: Context) -> None:
    user = await ctx.db.customers.get_customer_by_id(ctx.event.from_user.id)
    if not user:
        await callback.answer()
        return

    user.lang = callback.data
    ctx.lang = callback.data

    await ctx.db.update(user)

    await callback.message.delete()

    await call_state_handler(CommonStates.currency_choosing,
                       ctx)

    await callback.answer()

@router.callback_query(CommonStates.currency_choosing)
async def currency_choosing_handler(callback: CallbackQuery, ctx: Context) -> None:
    user = await ctx.db.customers.get_customer_by_id(ctx.event.from_user.id)
    user.balance.selected_currency = callback.data

    await ctx.db.update(user)

    await callback.message.delete()

    await call_state_handler(CommonStates.main_menu,
                             ctx)

    await callback.answer()

@router.message(CommonStates.main_menu, lambda message: (message.text.lower() in CommonTranslates.about_menu.values()) if message.text else False)
async def about_command_handler(message: Message, ctx: Context) -> None:

    await message.reply(**as_list(
        BlockQuote(Bold("PLACEHOLDER")),
        Text("Lorem ipsum dolor sit amed.")
    ).as_kwargs(), reply_markup=CommonKBs.main_menu(ctx.lang))

    await ctx.fsm.set_state(CommonStates.main_menu)

@router.message(CommonStates.main_menu, lambda message: (message.text in ReplyButtonsTranslates.assortment.values()) if message.text else False)
async def assortment_command_handler(message: Message, ctx: Context) -> None:
    await call_state_handler(MainMenuOptions.Assortment, ctx)

@router.message(CommonStates.main_menu)
async def bad_menu_handler(message: Message, ctx: Context) -> None:
    await call_state_handler(CommonStates.main_menu, 
                       ctx)

