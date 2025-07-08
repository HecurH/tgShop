from aiogram import Router
from src.classes.config import SUPPORTED_CURRENCIES, SUPPORTED_LANGUAGES_TEXT
from src.classes.helper_classes import Context
from src.classes.states import CommonStates, MainMenuOptions, Profile, call_state_handler
from src.classes.translates import *

router = Router(name="profile")



@router.message(CommonStates.MainMenu, lambda message: (message.text in ReplyButtonsTranslates.profile.values()) if message.text else False)
async def profile_entrance_handler(_, ctx: Context) -> None:
    await call_state_handler(MainMenuOptions.Profile, ctx)
    
    
@router.message(MainMenuOptions.Profile)
async def profile_command_handler(_, ctx: Context) -> None:
    actions = {
        UncategorizedTranslates.translate("back", ctx.lang): CommonStates.MainMenu,
        ReplyButtonsTranslates.Profile.translate("settings", ctx.lang): Profile.Settings.Menu,
        ReplyButtonsTranslates.Profile.translate("delivery", ctx.lang): Profile.Delivery.Menu
    }
    next_state = actions.get(ctx.message.text)
    if next_state is not None:
        await call_state_handler(next_state, ctx)
    else:
        await call_state_handler(MainMenuOptions.Profile, ctx)
    
@router.message(Profile.Settings.Menu)
async def profile_command_handler(_, ctx: Context) -> None:
    actions = {
        UncategorizedTranslates.translate("back", ctx.lang): MainMenuOptions.Profile,
        ReplyButtonsTranslates.Profile.Settings.translate("lang", ctx.lang): Profile.Settings.ChangeLanguage,
        ReplyButtonsTranslates.Profile.Settings.translate("currency", ctx.lang): Profile.Settings.ChangeCurrency,
    }
    next_state = actions.get(ctx.message.text)
    if next_state is not None:
        await call_state_handler(next_state, ctx)
    else:
        await call_state_handler(Profile.Settings.Menu, ctx)
        
@router.message(Profile.Delivery.Menu)
async def delivery_command_handler(_, ctx: Context) -> None:
    if ctx.message.text == UncategorizedTranslates.translate("back", ctx.lang):
        await call_state_handler(MainMenuOptions.Profile, ctx)
        return
    
    if ctx.message.text == ReplyButtonsTranslates.Profile.Delivery.translate("menu_not_set", ctx.lang) and not ctx.customer.delivery_info.service:
        
        await ctx.fsm.update_data(delivery_first_setup=True)
        await call_state_handler(Profile.Delivery.Editables.IsForeign, ctx)
        return
    
    
    await call_state_handler(Profile.Delivery.Menu, ctx)
    
@router.message(Profile.Settings.ChangeLanguage)
async def profile_change_lang_handler(_, ctx: Context) -> None:
    if ctx.message.text == UncategorizedTranslates.translate("back", ctx.lang):
        await call_state_handler(Profile.Settings.Menu, ctx)
        return
    
    if ctx.message.text in SUPPORTED_LANGUAGES_TEXT.keys():
        ctx.customer.lang = SUPPORTED_LANGUAGES_TEXT.get(ctx.message.text)
        ctx.lang = SUPPORTED_LANGUAGES_TEXT.get(ctx.message.text)
        await ctx.db.update(ctx.customer)
        
        await ctx.message.answer(ProfileTranslates.Settings.translate("lang_changed", ctx.lang))
        await call_state_handler(Profile.Settings.Menu, ctx)
        return
    
    await call_state_handler(Profile.Settings.ChangeLanguage, ctx)
    
@router.message(Profile.Settings.ChangeCurrency)
async def profile_change_lang_handler(_, ctx: Context) -> None:
    if ctx.message.text == UncategorizedTranslates.translate("back", ctx.lang):
        await call_state_handler(Profile.Settings.Menu, ctx)
        return
    
    if ctx.message.text in UncategorizedTranslates.Currencies.get_all_attributes(ctx.lang):
        ctx.customer.currency = UncategorizedTranslates.Currencies.get_attribute(ctx.message.text, ctx.lang)
        await ctx.db.update(ctx.customer)
        
        await ctx.message.answer(ProfileTranslates.Settings.translate("currency_changed", ctx.lang).format(currency=ctx.message.text))
        await call_state_handler(Profile.Settings.Menu, ctx)
        return
    
    await call_state_handler(Profile.Settings.ChangeCurrency, ctx)

@router.message(Profile.Delivery.Editables.IsForeign)
async def editable_is_foreign_handler(_, ctx: Context) -> None:
    first_setup = ctx.customer.delivery_info.service is None
    
    if ctx.message.text == UncategorizedTranslates.translate("back", ctx.lang) or ctx.message.text == UncategorizedTranslates.translate("cancel", ctx.lang) and not first_setup:
        await ctx.fsm.set_data({})
        await call_state_handler(Profile.Delivery.Menu, ctx)
        return
    
    if ctx.message.text == ProfileTranslates.Delivery.translate("foreign_choice_foreign", ctx.lang):
        is_foreign = True
    elif ctx.message.text == ProfileTranslates.Delivery.translate("foreign_choice_rus", ctx.lang):
        is_foreign = False
    else:
        await ctx.message.delete()
        return
    
    if not first_setup and ctx.customer.delivery_info.is_foreign == is_foreign:
        await ctx.message.answer(UncategorizedTranslates.translate("ok_dont_changing", ctx.lang))
        await call_state_handler(Profile.Delivery.Menu, ctx)
        return
    
    
    # при изменении этого параметра все равно надо менять сервис доставки
    await call_state_handler(Profile.Delivery.Editables.Service, ctx)
    

@router.message(Profile.Delivery.Editables.Service)
async def editable_service_handler(_, ctx: Context) -> None:
    first_setup = ctx.customer.delivery_info.service is None
    
    if ctx.message.text == UncategorizedTranslates.translate("back", ctx.lang) or ctx.message.text == UncategorizedTranslates.translate("cancel", ctx.lang) and not first_setup:
        await ctx.fsm.set_data({})
        await call_state_handler(Profile.Delivery.Menu, ctx)
        return
    
    if ctx.message.text == ProfileTranslates.Delivery.translate("foreign_choice_foreign", ctx.lang):
        is_foreign = True
    elif ctx.message.text == ProfileTranslates.Delivery.translate("foreign_choice_rus", ctx.lang):
        is_foreign = False
    else:
        await ctx.message.delete()
        return
    
    if not first_setup and ctx.customer.delivery_info.is_foreign == is_foreign:
        await ctx.message.answer(UncategorizedTranslates.translate("ok_dont_changing", ctx.lang))
        await call_state_handler(Profile.Delivery.Menu, ctx)
        return
    
    
    # при изменении этого параметра все равно надо менять сервис доставки
    await call_state_handler(Profile.Delivery.Editables.Service, ctx)