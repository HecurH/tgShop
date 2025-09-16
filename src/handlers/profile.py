from typing import Iterable
from aiogram import Router
from schemas.db_models import *

from configs.supported import SUPPORTED_LANGUAGES_TEXT
from core.helper_classes import Context
from core.states import Cart, CommonStates, Profile, call_state_handler
from ui.translates import ProfileTranslates, ReplyButtonsTranslates, UncategorizedTranslates

router = Router(name="profile")



@router.message(CommonStates.MainMenu, lambda message: (message.text in ReplyButtonsTranslates.profile.values()) if message.text else False)
async def profile_entrance_handler(_, ctx: Context) -> None:
    await call_state_handler(Profile.Menu, ctx)
    
    
@router.message(Profile.Menu)
async def profile_command_handler(_, ctx: Context) -> None:
    match ctx.message.text:
        case ctx.t.UncategorizedTranslates.back:
            await call_state_handler(CommonStates.MainMenu, ctx)
        case ctx.t.ReplyButtonsTranslates.Profile.settings:
            await call_state_handler(Profile.Settings.Menu, ctx)
        case ctx.t.ReplyButtonsTranslates.Profile.referrals:
            if await ctx.services.db.inviters.check_customer(ctx.customer.id):
                await call_state_handler(Profile.Referrals.Menu, ctx)
                return
            await call_state_handler(Profile.Referrals.AskForJoin, ctx)
        case ctx.t.ReplyButtonsTranslates.Profile.delivery:
            await call_state_handler(Profile.Delivery.Menu, ctx)
        case _:
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
        await ctx.services.db.update(ctx.customer)
        
        text = ProfileTranslates.Settings.lang_changed.translate(ctx.lang) # тк тут ctx.t уже В-С-Е
        
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
        await ctx.services.db.update(ctx.customer)
        
        text = ctx.t.ProfileTranslates.Settings.currency_changed.format(currency=ctx.message.text)
        await call_state_handler(Profile.Settings.Menu, ctx, send_before=(text, 1))
        return
    
    await call_state_handler(Profile.Settings.ChangeCurrency, ctx)

@router.message(Profile.Referrals.AskForJoin)
async def referrals_ask_for_join_handler(_, ctx: Context) -> None:
    if ctx.message.text == ctx.t.UncategorizedTranslates.back:
        await call_state_handler(Profile.Menu, ctx)
        return

    if ctx.message.text == ctx.t.UncategorizedTranslates.what_is_this:
        await call_state_handler(Profile.Referrals.AskForJoin, ctx, send_before=(ctx.t.ProfileTranslates.Referrals.what_is_this, 1.5))
        return
    if ctx.message.text != ctx.t.UncategorizedTranslates.yes:
        await call_state_handler(Profile.Referrals.AskForJoin, ctx)
        return
    
    inviter = await ctx.services.db.inviters.new(ctx.customer.id)
    await call_state_handler(Profile.Referrals.Menu, ctx, inviter=inviter)
    
@router.message(Profile.Referrals.Menu)
async def referrals_menu_handler(_, ctx: Context) -> None:
    if ctx.message.text == ctx.t.UncategorizedTranslates.back:
        await call_state_handler(Profile.Menu, ctx)
        return
    inviter = await ctx.services.db.inviters.get_inviter_by_customer_id(ctx.customer.id)

    if ctx.message.text == ctx.t.ReplyButtonsTranslates.Profile.Referrals.invitation_link:
        await call_state_handler(Profile.Referrals.InvitationLinkView, ctx, inviter=inviter)
        return
    
    await call_state_handler(Profile.Referrals.Menu, ctx, inviter=inviter)

@router.message(Profile.Referrals.InvitationLinkView)
async def referrals_invitation_link_view_handler(_, ctx: Context) -> None:
    if ctx.message.text == ctx.t.UncategorizedTranslates.back:
        await call_state_handler(Profile.Referrals.Menu, ctx)
        return

@router.message(Profile.Delivery.Menu)
async def delivery_command_handler(_, ctx: Context) -> None:
    text = ctx.message.text
    delivery_info = ctx.customer.delivery_info
    
    if text == ctx.t.UncategorizedTranslates.back:
        await call_state_handler(Profile.Menu, ctx)
        return
    
    if ctx.customer.waiting_for_manual_delivery_info_confirmation:
        await call_state_handler(Profile.Menu, ctx, send_before=(ctx.t.ProfileTranslates.Delivery.waiting_for_manual_confirmation, 1))
        return
    
    if text == ctx.t.ReplyButtonsTranslates.Profile.Delivery.menu_not_set and not delivery_info:
        await call_state_handler(Profile.Delivery.Editables.IsForeign, ctx)
        return
    
    if not delivery_info:
        await call_state_handler(Profile.Delivery.Menu, ctx)
        return
    
    if text.split()[0] == ctx.t.ReplyButtonsTranslates.Profile.Delivery.Edit.foreign:
        await call_state_handler(Profile.Delivery.Editables.IsForeign, ctx)
        return
    elif text == delivery_info.service.name.get(ctx):
        await delivery_info.save_in_fsm(ctx, "delivery_info")
        await call_state_handler(Profile.Delivery.Editables.Service, ctx, delivery_info=delivery_info, is_foreign_services=delivery_info.service.is_foreign)
        return
    elif text == delivery_info.service.selected_option.name.get(ctx):
        await delivery_info.save_in_fsm(ctx, "delivery_info")
        await call_state_handler(Profile.Delivery.Editables.RequirementsLists, ctx, delivery_info=delivery_info)
        return
    elif text == ctx.t.ReplyButtonsTranslates.Profile.Delivery.Edit.change_data:
        await delivery_info.save_in_fsm(ctx, "delivery_info")
        await ctx.fsm.update_data(requirement_index=0)
        await call_state_handler(Profile.Delivery.Editables.Requirement, ctx, delivery_info=delivery_info, requirement_index=0)
        return
    elif text == ctx.t.ReplyButtonsTranslates.Profile.Delivery.Edit.delete:
        await call_state_handler(Profile.Delivery.DeleteConfimation, ctx)
        return 
    
    
    
    await call_state_handler(Profile.Delivery.Menu, ctx)
    
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
    
    if not first_setup and ctx.customer.delivery_info.service and ctx.customer.delivery_info.service.is_foreign == is_foreign:
        await ctx.fsm.update_data(requirement_index=None, delivery_info=None)
        await call_state_handler(Profile.Delivery.Menu, ctx, send_before=(ctx.t.UncategorizedTranslates.ok_dont_changing, 1))
        return
    
    
    # при изменении этого параметра все равно надо менять сервис доставки
    delivery_info = ctx.customer.delivery_info or DeliveryInfo()
    
    await delivery_info.save_in_fsm(ctx, "delivery_info")
    await ctx.fsm.update_data(is_foreign=is_foreign)
    
    await call_state_handler(Profile.Delivery.Editables.Service, ctx, is_foreign_services=is_foreign)
    
@router.message(Profile.Delivery.Editables.Service)
async def editable_service_handler(_, ctx: Context) -> None:
    first_setup = ctx.customer.delivery_info is None
    delivery_info = await DeliveryInfo.from_fsm_context(ctx, "delivery_info")
    
    fsm_foreign = await ctx.fsm.get_value("is_foreign")
    is_foreign = bool(fsm_foreign) if fsm_foreign is not None else ctx.customer.delivery_info.service.is_foreign

    if ctx.message.text in [ctx.t.UncategorizedTranslates.back, ctx.t.UncategorizedTranslates.cancel]:
        await ctx.fsm.update_data(requirement_index=None, delivery_info=None)
        
        if first_setup:
            await call_state_handler(Profile.Delivery.Editables.IsForeign, ctx)
        else:
            await call_state_handler(Profile.Delivery.Menu, ctx)
        return


    services: Iterable[DeliveryService] = await ctx.services.db.delivery_services.get_all(is_foreign)
    service_name = ctx.message.text.rsplit(" ", 1)[0]
    service = next((ser for ser in services if ser.name.get(ctx) == service_name), None)
    
    if service is None:
        await call_state_handler(Profile.Delivery.Editables.Service, ctx, delivery_info=delivery_info, is_foreign_services=is_foreign)
        return

    if not first_setup and delivery_info.service.name == service.name:
        await ctx.fsm.update_data(requirement_index=None, delivery_info=None)
        await call_state_handler(Profile.Delivery.Menu, ctx, send_before=(ctx.t.UncategorizedTranslates.ok_dont_changing, 1))
        return
    
    delivery_info.service = service

    await delivery_info.save_in_fsm(ctx, "delivery_info")
    await call_state_handler(Profile.Delivery.Editables.RequirementsLists, ctx, ctx, delivery_info=delivery_info)
    
@router.message(Profile.Delivery.Editables.RequirementsLists)
async def editable_requirements_lists_handler(_, ctx: Context) -> None:
    first_setup = ctx.customer.delivery_info is None
    delivery_info: DeliveryInfo = await DeliveryInfo.from_fsm_context(ctx, "delivery_info")
    fsm_foreign = await ctx.fsm.get_value("is_foreign")
    fsm_foreign = await ctx.fsm.get_value("is_foreign")
    is_foreign = bool(fsm_foreign) if fsm_foreign is not None else ctx.customer.delivery_info.service.is_foreign

    if ctx.message.text in [ctx.t.UncategorizedTranslates.back, ctx.t.UncategorizedTranslates.cancel]:

        if first_setup:      
            await call_state_handler(Profile.Delivery.Editables.Service, ctx, delivery_info=delivery_info, is_foreign_services=is_foreign)
        else:  
            await ctx.fsm.update_data(requirement_index=None, delivery_info=None)
            await call_state_handler(Profile.Delivery.Menu, ctx)
        return

    lists = delivery_info.service.requirements_options
    req_list = next((lst for lst in lists if lst.name.get(ctx) == ctx.message.text), None)
    
    if req_list is None:
        await call_state_handler(Profile.Delivery.Editables.RequirementsLists, ctx, delivery_info=delivery_info)
        return
    
    if not first_setup and delivery_info.service.selected_option and delivery_info.service.selected_option.name == req_list.name:
        await ctx.fsm.update_data(requirement_index=None, delivery_info=None)
        await call_state_handler(Profile.Delivery.Menu, ctx, send_before=(ctx.t.UncategorizedTranslates.ok_dont_changing, 1))
        return
    
    delivery_info.service.selected_option = req_list

    await delivery_info.save_in_fsm(ctx, "delivery_info")
    await ctx.fsm.update_data(requirement_index=0)
    await call_state_handler(Profile.Delivery.Editables.Requirement, ctx, delivery_info=delivery_info, requirement_index=0)

@router.message(Profile.Delivery.Editables.Requirement)
async def editable_requirement_handler(_, ctx: Context) -> None:
    text = await ctx.parse_user_input()
    if text is None: return
    
    first_setup = ctx.customer.delivery_info is None
    delivery_info: DeliveryInfo = await DeliveryInfo.from_fsm_context(ctx, "delivery_info")

    if text in [ctx.t.UncategorizedTranslates.back, ctx.t.UncategorizedTranslates.cancel]:
        if first_setup:
            await call_state_handler(Profile.Delivery.Editables.RequirementsLists, ctx, delivery_info=delivery_info)
        else:        
            await ctx.fsm.update_data(requirement_index=None, delivery_info=None)
            await call_state_handler(Profile.Delivery.Menu, ctx)
        return
    
    requirement_index = await ctx.fsm.get_value("requirement_index")

    requirement: DeliveryRequirement = delivery_info.service.selected_option.requirements[requirement_index]
    if text.isdigit():
        await call_state_handler(Profile.Delivery.Editables.Requirement, ctx, delivery_info=delivery_info, requirement_index=requirement_index)
        return
    
    requirement.value.update(text)
    
    if len(delivery_info.service.selected_option.requirements)-1 == requirement_index:
        await ctx.fsm.update_data(requirement_index=None)
        if delivery_info.service.requires_manual_confirmation:
            await delivery_info.save_in_fsm(ctx, "delivery_info")
            await call_state_handler(Profile.Delivery.Editables.SendToManualConfirmation, ctx, delivery_info=delivery_info)
            return

        
        
        ctx.customer.delivery_info = delivery_info
        await ctx.services.db.customers.save(ctx.customer)
        
        if await ctx.fsm.get_value("back_to_cart_after_delivery"):
            await ctx.fsm.update_data(back_to_cart_after_delivery=None)
            await call_state_handler(Cart.Menu, ctx, current=await ctx.fsm.get_value("current") or 1)
            return
        
        
        
        await call_state_handler(Profile.Delivery.Menu, ctx)
        return
        

    await delivery_info.save_in_fsm(ctx, "delivery_info")
    await ctx.fsm.update_data(requirement_index=requirement_index+1)
    await call_state_handler(Profile.Delivery.Editables.Requirement, ctx, delivery_info=delivery_info, requirement_index=requirement_index+1)
    
@router.message(Profile.Delivery.Editables.SendToManualConfirmation)
async def editable_send_to_manual_confirmation_handler(_, ctx: Context) -> None:
    if ctx.message.text != ctx.t.UncategorizedTranslates.yes:
        await call_state_handler(Profile.Delivery.Menu, ctx)
        return
    
    delivery_info: DeliveryInfo = await DeliveryInfo.from_fsm_context(ctx, "delivery_info")
    
    await ctx.services.notificators.AdminChatNotificator.send_delivery_manual_price_confirmation(delivery_info, ctx)
    
    ctx.customer.delivery_info = None
    ctx.customer.waiting_for_manual_delivery_info_confirmation = True
    await ctx.services.db.customers.save(ctx.customer)
    
    await call_state_handler(CommonStates.MainMenu, ctx, send_before=(ctx.t.ProfileTranslates.delivery_info_price_sent_to_confirmation, 1))
    
@router.message(Profile.Delivery.DeleteConfimation)
async def delete_confimation_handler(_, ctx: Context) -> None:
    if ctx.message.text != ctx.t.UncategorizedTranslates.yes: 
        await call_state_handler(Profile.Delivery.Menu, ctx)
        return
    
    ctx.customer.delivery_info = None
    
    await ctx.services.db.customers.save(ctx.customer)
    
    await call_state_handler(Profile.Delivery.Menu, ctx)