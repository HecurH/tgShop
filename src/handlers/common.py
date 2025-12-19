import contextlib
import logging
from aiogram import Router
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.types import CallbackQuery, ErrorEvent
from aiogram.utils.formatting import as_list, Bold, BlockQuote, Text

from configs.supported import SUPPORTED_LANGUAGES_TEXT
from core.helper_classes import Context
from ui.keyboards import CommonKBs
from core.states import CommonStates, NewUserStates, call_state_handler
from ui.translates import ReplyButtonsTranslates, TranslatorHub

router = Router(name="common")



@router.message(Command("start"))
@router.message(CommandStart(deep_link=True))
async def command_start_handler(_, ctx: Context, command: CommandObject) -> None:
    await ctx.fsm.clear()

    user = await ctx.services.db.customers.find_by_user_id(ctx.message.from_user.id)
    if not user:
        inviter = await ctx.services.db.inviters.find_inviter_by_deep_link(command.args) if command.args else None
        if inviter: await ctx.services.db.inviters.count_new_customer(inviter)
            
        
        ctx.customer = await ctx.services.db.customers.new_customer(
            user_id=ctx.message.from_user.id,
            inviter=inviter or None,
            lang="?",
            currency="RUB"
        )
        
    if ctx.lang == "?":
        lang = ctx.message.from_user.language_code.split("-")[0]
        if lang in SUPPORTED_LANGUAGES_TEXT.values():
            ctx.customer.lang = lang
            ctx.lang = lang
            ctx.t = TranslatorHub.get_for_lang(lang, ctx.services.placeholders)

            await ctx.services.db.customers.save(ctx.customer)
            await call_state_handler(NewUserStates.AskAge, ctx)
            return
        
        await call_state_handler(NewUserStates.LangChoosing, 
                           ctx)
        return
    
    await ctx.message.reply(ctx.t.CommonTranslates.hi)

    await call_state_handler(CommonStates.MainMenu, 
                       ctx)

@router.callback_query(NewUserStates.LangChoosing)
async def lang_changing_handler(callback: CallbackQuery, ctx: Context) -> None:
    if not ctx.customer:
        await callback.answer()
        return

    ctx.customer.lang = callback.data
    ctx.lang = callback.data

    await ctx.services.db.customers.save(ctx.customer)

    await callback.message.delete()

    await call_state_handler(NewUserStates.AskAge, ctx)

    await callback.answer()
    
@router.callback_query(NewUserStates.AskAge)
async def ask_age_handler(callback: CallbackQuery, ctx: Context) -> None:
    text = callback.data
    await callback.answer()
    
    if text == "yes":
        await call_state_handler(NewUserStates.CurrencyChoosing, ctx)
    elif text == "no":
        ctx.customer.banned = True
        await ctx.services.db.customers.save(ctx.customer)
        await ctx.message.answer(ctx.t.CommonTranslates.age_restriction)
        
    await callback.message.delete()

    

@router.callback_query(NewUserStates.CurrencyChoosing)
async def currency_choosing_handler(callback: CallbackQuery, ctx: Context) -> None:
    await ctx.customer.change_selected_currency(callback.data, ctx, do_timeout=False)

    await ctx.services.db.customers.save(ctx.customer)

    await callback.message.delete()

    await call_state_handler(CommonStates.MainMenu,
                             ctx)

    await callback.answer()

@router.message(CommonStates.MainMenu, lambda message: (message.text in ReplyButtonsTranslates.about.values()) if message.text else False)
async def about_command_handler(_, ctx: Context) -> None:
    await ctx.message.answer(ctx.t.CommonTranslates.about_us)
    
    await call_state_handler(CommonStates.MainMenu,
                             ctx)
    
@router.error()
async def global_error_handler(event: ErrorEvent):
    with contextlib.suppress(Exception):
        if hasattr(event.update, "message") and event.update.message:
            await event.update.message.reply("Произошла ошибка. Пожалуйста, попробуйте позже.\nЕсли ошибка повторяется, напишите @HecurH.")
        elif hasattr(event.update, "callback_query") and event.update.callback_query:
            await event.update.callback_query.answer("Произошла ошибка. Пожалуйста, попробуйте позже.", show_alert=True)

    logging.getLogger(__name__).exception(f"Ошибка в хендлере: {event.exception}")
