from typing import Iterable
from aiogram import Router
from src.classes.db_models import DeliveryInfo, DeliveryRequirement, DeliveryService
from src.classes.config import SUPPORTED_LANGUAGES_TEXT
from src.classes.helper_classes import Context
from src.classes.states import CommonStates, Profile, call_state_handler
from src.classes.translates import *

router = Router(name="profile")



@router.message(CommonStates.MainMenu, lambda message: (message.text in ReplyButtonsTranslates.profile.values()) if message.text else False)
async def profile_entrance_handler(_, ctx: Context) -> None:
    await call_state_handler(Profile.Menu, ctx)
    
    
@router.message(Profile.Menu)
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
        await call_state_handler(Profile.Menu, ctx)
    
@router.message(Profile.Settings.Menu)
async def profile_command_handler(_, ctx: Context) -> None:
    actions = {
        UncategorizedTranslates.translate("back", ctx.lang): Profile.Menu,
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
    text = ctx.message.text
    delivery_info = ctx.customer.delivery_info
    
    if text == UncategorizedTranslates.translate("back", ctx.lang):
        await call_state_handler(Profile.Menu, ctx)
        return
    
    if text == ReplyButtonsTranslates.Profile.Delivery.translate("menu_not_set", ctx.lang) and not delivery_info.service:
        await call_state_handler(Profile.Delivery.Editables.IsForeign, ctx)
        return
    
    
    if text.split()[0] == ReplyButtonsTranslates.Profile.Delivery.Edit.translate("foreign", ctx.lang):
        await call_state_handler(Profile.Delivery.Editables.IsForeign, ctx)
        return
    elif text == delivery_info.service.name.data[ctx.lang]:
        await ctx.fsm.update_data(delivery_info=delivery_info.model_dump())
        await call_state_handler(Profile.Delivery.Editables.Service, ctx)
        return
    elif text == delivery_info.service.selected_option.name.data[ctx.lang]:
        await ctx.fsm.update_data(delivery_info=delivery_info.model_dump())
        await call_state_handler(Profile.Delivery.Editables.RequirementsLists, ctx)
        return
    elif text == ReplyButtonsTranslates.Profile.Delivery.Edit.translate("change_data", ctx.lang):
        await ctx.fsm.update_data(delivery_info=delivery_info.model_dump())
        await ctx.fsm.update_data(requirement_index=0)
        await call_state_handler(Profile.Delivery.Editables.Requirement, ctx)
        return
    elif text == ReplyButtonsTranslates.Profile.Delivery.Edit.translate("delete", ctx.lang):
        await call_state_handler(Profile.Delivery.DeleteConfimation, ctx)
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
        
        text = ProfileTranslates.Settings.translate("lang_changed", ctx.lang)
        await call_state_handler(Profile.Settings.Menu, ctx, send_before=text)
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
        
        text = ProfileTranslates.Settings.translate("currency_changed", ctx.lang).format(currency=ctx.message.text)
        await call_state_handler(Profile.Settings.Menu, ctx, send_before=text)
        return
    
    await call_state_handler(Profile.Settings.ChangeCurrency, ctx)

@router.message(Profile.Delivery.Editables.IsForeign)
async def editable_is_foreign_handler(_, ctx: Context) -> None:
    first_setup = ctx.customer.delivery_info.service is None
    
    if ctx.message.text in [UncategorizedTranslates.translate("back", ctx.lang), UncategorizedTranslates.translate("cancel", ctx.lang)]:
        await ctx.fsm.update_data(requirement_index=None, delivery_info=None)
        await call_state_handler(Profile.Delivery.Menu, ctx)
        return
    
    if ctx.message.text == ProfileTranslates.Delivery.translate("foreign_choice_foreign", ctx.lang):
        is_foreign = True
    elif ctx.message.text == ProfileTranslates.Delivery.translate("foreign_choice_rus", ctx.lang):
        is_foreign = False
    else:
        
        await call_state_handler(Profile.Delivery.Editables.IsForeign, ctx)
        return
    
    if not first_setup and ctx.customer.delivery_info.is_foreign == is_foreign:
        await ctx.fsm.update_data(requirement_index=None, delivery_info=None)
        await call_state_handler(Profile.Delivery.Menu, ctx, send_before=UncategorizedTranslates.translate("ok_dont_changing", ctx.lang))
        return
    
    
    # при изменении этого параметра все равно надо менять сервис доставки
    info = ctx.customer.delivery_info
    info.is_foreign = is_foreign
    
    await ctx.fsm.update_data(delivery_info=info.model_dump())
    await call_state_handler(Profile.Delivery.Editables.Service, ctx)
    
@router.message(Profile.Delivery.Editables.Service)
async def editable_service_handler(_, ctx: Context) -> None:
    first_setup = ctx.customer.delivery_info.service is None
    delivery_info = DeliveryInfo(**await ctx.fsm.get_value("delivery_info"))

    if ctx.message.text in [UncategorizedTranslates.translate("back", ctx.lang), UncategorizedTranslates.translate("cancel", ctx.lang)]:
        await ctx.fsm.update_data(requirement_index=None, delivery_info=None)
        
        if first_setup:
            await call_state_handler(Profile.Delivery.Editables.IsForeign, ctx)
        else:
            await call_state_handler(Profile.Delivery.Menu, ctx)
        return


    services: Iterable[DeliveryService] = await ctx.db.delivery_services.get_all(delivery_info.is_foreign)
    service_name = ctx.message.text.rsplit(" ", 1)[0]
    service = next((ser for ser in services if ser.name.data[ctx.lang] == service_name), None)
    
    if service is None:
        await call_state_handler(Profile.Delivery.Editables.Service, ctx)
        return

    if not first_setup and delivery_info.service.name == service.name:
        await ctx.fsm.update_data(requirement_index=None, delivery_info=None)
        await call_state_handler(Profile.Delivery.Menu, ctx, send_before=UncategorizedTranslates.translate("ok_dont_changing", ctx.lang))
        return
    
    delivery_info.service = service

    await ctx.fsm.update_data(delivery_info=delivery_info.model_dump())
    await call_state_handler(Profile.Delivery.Editables.RequirementsLists, ctx)
    
@router.message(Profile.Delivery.Editables.RequirementsLists)
async def editable_requirements_lists_handler(_, ctx: Context) -> None:
    first_setup = ctx.customer.delivery_info.service is None
    delivery_info = DeliveryInfo(**await ctx.fsm.get_value("delivery_info"))

    if ctx.message.text in [UncategorizedTranslates.translate("back", ctx.lang), UncategorizedTranslates.translate("cancel", ctx.lang)]:

        if first_setup:      
            await call_state_handler(Profile.Delivery.Editables.Service, ctx)
        else:  
            await ctx.fsm.update_data(requirement_index=None, delivery_info=None)
            await call_state_handler(Profile.Delivery.Menu, ctx)
        return

    lists = delivery_info.service.requirements_options
    req_list = next((lst for lst in lists if lst.name.data[ctx.lang] == ctx.message.text), None)
    
    if req_list is None:
        await call_state_handler(Profile.Delivery.Editables.RequirementsLists, ctx)
        return
    
    if not first_setup and delivery_info.service.selected_option and delivery_info.service.selected_option.name == req_list.name:
        await ctx.fsm.update_data(requirement_index=None, delivery_info=None)
        await call_state_handler(Profile.Delivery.Menu, ctx, send_before=UncategorizedTranslates.translate("ok_dont_changing", ctx.lang))
        return
    
    delivery_info.service.selected_option = req_list

    await ctx.fsm.update_data(delivery_info=delivery_info.model_dump())
    await ctx.fsm.update_data(requirement_index=0)
    await call_state_handler(Profile.Delivery.Editables.Requirement, ctx)

@router.message(Profile.Delivery.Editables.Requirement)
async def editable_requirement_handler(_, ctx: Context) -> None:
    first_setup = ctx.customer.delivery_info.service is None
    delivery_info = DeliveryInfo(**await ctx.fsm.get_value("delivery_info"))

    if ctx.message.text in [UncategorizedTranslates.translate("back", ctx.lang), UncategorizedTranslates.translate("cancel", ctx.lang)]:
        if first_setup:
            await call_state_handler(Profile.Delivery.Editables.RequirementsLists, ctx)
        else:        
            await ctx.fsm.update_data(requirement_index=None, delivery_info=None)
            await call_state_handler(Profile.Delivery.Menu, ctx)
        return
    
    requirement_index = await ctx.fsm.get_value("requirement_index")

    requirement: DeliveryRequirement = delivery_info.service.selected_option.requirements[requirement_index]
    if ctx.message.text.isdigit():
        await call_state_handler(Profile.Delivery.Editables.Requirement, ctx)
        return
    
    requirement.value.update(ctx.message.text)
    
    if len(delivery_info.service.selected_option.requirements)-1 == requirement_index:
        ctx.customer.delivery_info = delivery_info
        await ctx.db.customers.save(ctx.customer)
        
        await ctx.fsm.update_data(requirement_index=None, delivery_info=None)
        await call_state_handler(Profile.Delivery.Menu, ctx)
        return
        

    await ctx.fsm.update_data(delivery_info=delivery_info.model_dump())
    await ctx.fsm.update_data(requirement_index=requirement_index+1)
    await call_state_handler(Profile.Delivery.Editables.Requirement, ctx)
    

@router.message(Profile.Delivery.DeleteConfimation)
async def delete_confimation_handler(_, ctx: Context) -> None:

    if ctx.message.text != UncategorizedTranslates.translate("yes", ctx.lang): 
        await call_state_handler(Profile.Delivery.Menu, ctx)
        return
    
    ctx.customer.delivery_info.service = None
    
    await ctx.db.customers.save(ctx.customer)
    
    await call_state_handler(Profile.Delivery.Menu, ctx)