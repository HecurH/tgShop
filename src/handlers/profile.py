from typing import Iterable
from aiogram import Router
from schemas.db_models import *

from configs.supported import SUPPORTED_LANGUAGES_TEXT
from core.helper_classes import Context
from core.states import Cart, CommonStates, Profile, call_state_handler
from ui.translates import ReplyButtonsTranslates, UncategorizedTranslates

router = Router(name="profile")



@router.message(CommonStates.MainMenu, lambda message: (message.text in ReplyButtonsTranslates.profile.values()) if message.text else False)
async def profile_entrance_handler(_, ctx: Context) -> None:
    await call_state_handler(Profile.Menu, ctx)
    
    
@router.message(Profile.Menu)
async def profile_command_handler(_, ctx: Context) -> None:
    actions = {
        ctx.t.UncategorizedTranslates.back: CommonStates.MainMenu,
        ctx.t.ReplyButtonsTranslates.Profile.settings: Profile.Settings.Menu,
        ctx.t.ReplyButtonsTranslates.Profile.delivery: Profile.Delivery.Menu
    }
    next_state = actions.get(ctx.message.text)
    if next_state is not None:
        await call_state_handler(next_state, ctx)
    else:
        await call_state_handler(Profile.Menu, ctx)
    
@router.message(Profile.Settings.Menu)
async def profile_command_handler(_, ctx: Context) -> None:
    actions = {
        ctx.t.UncategorizedTranslates.back: Profile.Menu,
        ctx.t.ReplyButtonsTranslates.Profile.Settings.lang: Profile.Settings.ChangeLanguage,
        ctx.t.ReplyButtonsTranslates.Profile.Settings.currency: Profile.Settings.ChangeCurrency,
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
    
    if text == ctx.t.UncategorizedTranslates.back:
        await call_state_handler(Profile.Menu, ctx)
        return
    
    if text == ctx.t.ReplyButtonsTranslates.Profile.Delivery.menu_not_set and not delivery_info:
        await call_state_handler(Profile.Delivery.Editables.IsForeign, ctx)
        return
    
    
    if text.split()[0] == ctx.t.ReplyButtonsTranslates.Profile.Delivery.Edit.foreign:
        await call_state_handler(Profile.Delivery.Editables.IsForeign, ctx)
        return
    elif text == delivery_info.service.name.get(ctx.lang):
        await ctx.fsm.update_data(delivery_info=delivery_info.model_dump())
        await call_state_handler(Profile.Delivery.Editables.Service, ctx)
        return
    elif text == delivery_info.service.selected_option.name.get(ctx.lang):
        await ctx.fsm.update_data(delivery_info=delivery_info.model_dump())
        await call_state_handler(Profile.Delivery.Editables.RequirementsLists, ctx)
        return
    elif text == ctx.t.ReplyButtonsTranslates.Profile.Delivery.Edit.change_data:
        await ctx.fsm.update_data(delivery_info=delivery_info.model_dump())
        await ctx.fsm.update_data(requirement_index=0)
        await call_state_handler(Profile.Delivery.Editables.Requirement, ctx)
        return
    elif text == ctx.t.ReplyButtonsTranslates.Profile.Delivery.Edit.delete:
        await call_state_handler(Profile.Delivery.DeleteConfimation, ctx)
        return 
    
    
    
    await call_state_handler(Profile.Delivery.Menu, ctx)
    
@router.message(Profile.Settings.ChangeLanguage)
async def profile_change_lang_handler(_, ctx: Context) -> None:
    if ctx.message.text == ctx.t.UncategorizedTranslates.back:
        await call_state_handler(Profile.Settings.Menu, ctx)
        return
    
    if ctx.message.text in SUPPORTED_LANGUAGES_TEXT.keys():
        iso_code = SUPPORTED_LANGUAGES_TEXT.get(ctx.message.text)
        if ctx.lang == iso_code:
            await call_state_handler(Profile.Settings.Menu, ctx, send_before=(ctx.t.ProfileTranslates.Settings.nothing_changed, 1))
            return
        
        ctx.customer.lang = SUPPORTED_LANGUAGES_TEXT.get(ctx.message.text)
        ctx.lang = SUPPORTED_LANGUAGES_TEXT.get(ctx.message.text)
        await ctx.db.update(ctx.customer)
        
        text = ctx.t.ProfileTranslates.Settings.lang_changed
        await call_state_handler(Profile.Settings.Menu, ctx, send_before=(text, 1))
        return
    
    await call_state_handler(Profile.Settings.ChangeLanguage, ctx)
    
@router.message(Profile.Settings.ChangeCurrency)
async def profile_change_lang_handler(_, ctx: Context) -> None:
    if ctx.message.text == ctx.t.UncategorizedTranslates.back:
        await call_state_handler(Profile.Settings.Menu, ctx)
        return
    
    if ctx.message.text in UncategorizedTranslates.Currencies.get_all_attributes(ctx.lang):
        currency = UncategorizedTranslates.Currencies.get_attribute(ctx.message.text, ctx.lang)
        if ctx.customer.currency == currency:
            await call_state_handler(Profile.Settings.Menu, ctx, send_before=(ctx.t.ProfileTranslates.Settings.nothing_changed, 1))
            return
        
        ctx.customer.currency = currency
        await ctx.db.update(ctx.customer)
        
        text = ctx.t.ProfileTranslates.Settings.currency_changed.format(currency=ctx.message.text)
        await call_state_handler(Profile.Settings.Menu, ctx, send_before=(text, 1))
        return
    
    await call_state_handler(Profile.Settings.ChangeCurrency, ctx)

@router.message(Profile.Delivery.Editables.IsForeign)
async def editable_is_foreign_handler(_, ctx: Context) -> None:
    first_setup = ctx.customer.delivery_info is None
    
    if ctx.message.text in [ctx.t.UncategorizedTranslates.back, ctx.t.UncategorizedTranslates.cancel]:
        await ctx.fsm.update_data(requirement_index=None, delivery_info=None)
        await call_state_handler(Profile.Delivery.Menu, ctx)
        return
    
    if ctx.message.text == ctx.t.ProfileTranslates.Delivery.foreign_choice_foreign:
        is_foreign = True
    elif ctx.message.text == ctx.t.ProfileTranslates.Delivery.foreign_choice_rus:
        is_foreign = False
    else:
        
        await call_state_handler(Profile.Delivery.Editables.IsForeign, ctx)
        return
    
    if not first_setup and ctx.customer.delivery_info.is_foreign == is_foreign:
        await ctx.fsm.update_data(requirement_index=None, delivery_info=None)
        await call_state_handler(Profile.Delivery.Menu, ctx, send_before=(ctx.t.UncategorizedTranslates.ok_dont_changing, 1))
        return
    
    
    # при изменении этого параметра все равно надо менять сервис доставки
    info = ctx.customer.delivery_info or DeliveryInfo()
    info.is_foreign = is_foreign
    
    await ctx.fsm.update_data(delivery_info=info.model_dump())
    await call_state_handler(Profile.Delivery.Editables.Service, ctx)
    
@router.message(Profile.Delivery.Editables.Service)
async def editable_service_handler(_, ctx: Context) -> None:
    first_setup = ctx.customer.delivery_info is None
    delivery_info = DeliveryInfo(**await ctx.fsm.get_value("delivery_info"))

    if ctx.message.text in [ctx.t.UncategorizedTranslates.back, ctx.t.UncategorizedTranslates.cancel]:
        await ctx.fsm.update_data(requirement_index=None, delivery_info=None)
        
        if first_setup:
            await call_state_handler(Profile.Delivery.Editables.IsForeign, ctx)
        else:
            await call_state_handler(Profile.Delivery.Menu, ctx)
        return


    services: Iterable[DeliveryService] = await ctx.db.delivery_services.get_all(delivery_info.is_foreign)
    service_name = ctx.message.text.rsplit(" ", 1)[0]
    service = next((ser for ser in services if ser.name.get(ctx.lang) == service_name), None)
    
    if service is None:
        await call_state_handler(Profile.Delivery.Editables.Service, ctx)
        return

    if not first_setup and delivery_info.service.name == service.name:
        await ctx.fsm.update_data(requirement_index=None, delivery_info=None)
        await call_state_handler(Profile.Delivery.Menu, ctx, send_before=(ctx.t.UncategorizedTranslates.ok_dont_changing, 1))
        return
    
    delivery_info.service = service

    await ctx.fsm.update_data(delivery_info=delivery_info.model_dump())
    await call_state_handler(Profile.Delivery.Editables.RequirementsLists, ctx)
    
@router.message(Profile.Delivery.Editables.RequirementsLists)
async def editable_requirements_lists_handler(_, ctx: Context) -> None:
    first_setup = ctx.customer.delivery_info is None
    delivery_info = DeliveryInfo(**await ctx.fsm.get_value("delivery_info"))

    if ctx.message.text in [ctx.t.UncategorizedTranslates.back, ctx.t.UncategorizedTranslates.cancel]:

        if first_setup:      
            await call_state_handler(Profile.Delivery.Editables.Service, ctx)
        else:  
            await ctx.fsm.update_data(requirement_index=None, delivery_info=None)
            await call_state_handler(Profile.Delivery.Menu, ctx)
        return

    lists = delivery_info.service.requirements_options
    req_list = next((lst for lst in lists if lst.name.get(ctx.lang) == ctx.message.text), None)
    
    if req_list is None:
        await call_state_handler(Profile.Delivery.Editables.RequirementsLists, ctx)
        return
    
    if not first_setup and delivery_info.service.selected_option and delivery_info.service.selected_option.name == req_list.name:
        await ctx.fsm.update_data(requirement_index=None, delivery_info=None)
        await call_state_handler(Profile.Delivery.Menu, ctx, send_before=(ctx.t.UncategorizedTranslates.ok_dont_changing, 1))
        return
    
    delivery_info.service.selected_option = req_list

    await ctx.fsm.update_data(delivery_info=delivery_info.model_dump())
    await ctx.fsm.update_data(requirement_index=0)
    await call_state_handler(Profile.Delivery.Editables.Requirement, ctx)

@router.message(Profile.Delivery.Editables.Requirement)
async def editable_requirement_handler(_, ctx: Context) -> None:
    first_setup = ctx.customer.delivery_info is None
    delivery_info = DeliveryInfo(**await ctx.fsm.get_value("delivery_info"))

    if ctx.message.text in [ctx.t.UncategorizedTranslates.back, ctx.t.UncategorizedTranslates.cancel]:
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
        
        if await ctx.fsm.get_value("back_to_cart_after_delivery"):
            await ctx.fsm.update_data(back_to_cart_after_delivery=None)
            await call_state_handler(Cart.Menu, ctx, current=await ctx.fsm.get_value("current") or 1)
            return
        
        await call_state_handler(Profile.Delivery.Menu, ctx)
        return
        

    await ctx.fsm.update_data(delivery_info=delivery_info.model_dump())
    await ctx.fsm.update_data(requirement_index=requirement_index+1)
    await call_state_handler(Profile.Delivery.Editables.Requirement, ctx)
    
@router.message(Profile.Delivery.DeleteConfimation)
async def delete_confimation_handler(_, ctx: Context) -> None:

    if ctx.message.text != ctx.t.UncategorizedTranslates.yes: 
        await call_state_handler(Profile.Delivery.Menu, ctx)
        return
    
    ctx.customer.delivery_info = None
    
    await ctx.db.customers.save(ctx.customer)
    
    await call_state_handler(Profile.Delivery.Menu, ctx)