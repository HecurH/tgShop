from aiogram import Router
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.types import CallbackQuery
from aiogram.utils.formatting import as_list, Bold, BlockQuote, Text

from configs.supported import SUPPORTED_LANGUAGES_TEXT
from core.db import *
from core.helper_classes import Context
from ui.keyboards import CommonKBs
from core.states import CommonStates, NewUserStates, call_state_handler
from ui.translates import CommonTranslates, ReplyButtonsTranslates

router = Router(name="common")



@router.message(Command("start"))
@router.message(CommandStart(deep_link=True))
async def command_start_handler(_, ctx: Context, command: CommandObject) -> None:
    await ctx.fsm.clear()
    # print(ctx.message.from_user.language_code)

    user = await ctx.db.customers.get_customer_by_id(ctx.message.from_user.id)
    if not user:
        inviter = await ctx.db.get_one_by_query(Inviter, {"inviter_code": command.args}) if command.args else None
        
        ctx.customer = await ctx.db.customers.new_customer(
            user_id=ctx.message.from_user.id,
            inviter=inviter,
            lang="?",
            currency="RUB"
        )
        
    if ctx.lang == "?":
        lang = ctx.message.from_user.language_code.split("-")[0]
        print(lang)
        if lang in SUPPORTED_LANGUAGES_TEXT.values():
            ctx.customer.lang = lang
            ctx.lang = lang

            await ctx.db.update(ctx.customer)
            await call_state_handler(NewUserStates.CurrencyChoosing, ctx)
            return
        
        await call_state_handler(NewUserStates.LangChoosing, 
                           ctx)
        return
    await ctx.message.reply(CommonTranslates.translate("hi", ctx.lang))

    await call_state_handler(CommonStates.MainMenu, 
                       ctx)

@router.callback_query(NewUserStates.LangChoosing)
async def lang_changing_handler(callback: CallbackQuery, ctx: Context) -> None:
    if not ctx.customer:
        await callback.answer()
        return

    ctx.customer.lang = callback.data
    ctx.lang = callback.data

    await ctx.db.update(ctx.customer)

    await callback.message.delete()

    await call_state_handler(NewUserStates.CurrencyChoosing, ctx)

    await callback.answer()

@router.callback_query(NewUserStates.CurrencyChoosing)
async def currency_choosing_handler(callback: CallbackQuery, ctx: Context) -> None:
    await ctx.customer.change_selected_currency(callback.data, ctx.db.currency_converter)

    await ctx.db.update(ctx.customer)

    await callback.message.delete()

    await call_state_handler(CommonStates.MainMenu,
                             ctx)

    await callback.answer()

@router.message(CommonStates.MainMenu, lambda message: (message.text in ReplyButtonsTranslates.about.values()) if message.text else False)
async def about_command_handler(_, ctx: Context) -> None:

    await ctx.message.reply(**as_list(
        BlockQuote(Bold("PLACEHOLDER")),
        Text("Lorem ipsum dolor sit amed.")
    ).as_kwargs(), reply_markup=CommonKBs.main_menu(ctx.lang))

    await ctx.fsm.set_state(CommonStates.MainMenu)


# @router.message(CommonStates.main_menu)
# async def bad_menu_handler(message: Message, ctx: Context) -> None:
#     await call_state_handler(CommonStates.main_menu,
#                        ctx)

