import asyncio
from aiogram.fsm.state import StatesGroup, State
from typing import Callable, Dict, Any, Awaitable, Tuple, Union

from core.helper_classes import Context
from ui.message_tools import clear_keyboard_effect, send_media_response
from ui.texts import CartTextGen, ProfileTextGen, AssortmentTextGen, AssortmentTextGen
from ui.keyboards import *
from ui.translates import AssortmentTranslates, CartTranslates, CommonTranslates, ProfileTranslates


class StateHandlerRegistry:
    """Реестр обработчиков состояний."""

    def __init__(self):
        self._handlers: Dict[Any, Callable[..., Awaitable]] = {}

    def register(self, state):
        def decorator(func):
            self._handlers[state] = func
            return func

        return decorator

    def get(self, state):
        return self._handlers.get(state)

    def all_states(self):
        return list(self._handlers.keys())

    def all_handlers(self):
        return self._handlers.copy()


state_handlers = StateHandlerRegistry()


async def call_state_handler(state: State,
                             ctx: Context,
                             change_state = True,
                             send_before: Union[str, Tuple[str, float], None] = None,
                             **kwargs
                             ) -> None:
    """
    Вызывает обработчик состояния FSM. В случае ошибки уведомляет пользователя и возвращает в главное меню.
    """
    handler = state_handlers.get(state)
    if not handler:
        raise ValueError(f"Нет обработчика для состояния {state}")

    if change_state: await ctx.fsm.set_state(state)

    try:
        if send_before:
            if isinstance(send_before, str):
                await ctx.message.answer(send_before)
            elif isinstance(send_before, tuple):
                text, sleep_time = send_before
                
                await ctx.message.answer(text)
                await asyncio.sleep(sleep_time)
            
        await handler(ctx=ctx, **kwargs)

    except Exception as e:
        await ctx.message.answer(f"Error: {e}")
        await ctx.message.delete()
        if state != CommonStates.MainMenu:
            await call_state_handler(CommonStates.MainMenu, ctx)
        raise e


class NewUserStates(StatesGroup):
    LangChoosing = State()
    CurrencyChoosing = State()

@state_handlers.register(NewUserStates.LangChoosing)
async def handle_lang_choosing(ctx: Context, **_):
    await ctx.message.answer("Выберите язык:\n\nChoose language:",
                             reply_markup=CommonKBs.lang_choose())

@state_handlers.register(NewUserStates.CurrencyChoosing)
async def handle_currency_choosing(ctx: Context, **_):
    await ctx.message.answer(CommonTranslates.translate("currency_choosing", ctx.lang),
                             reply_markup=CommonKBs.currency_choose(ctx.lang))

class CommonStates(StatesGroup):
    MainMenu = State()

@state_handlers.register(CommonStates.MainMenu)
async def main_menu_handler(ctx: Context, **_):
    await ctx.message.answer(CommonTranslates.translate("heres_the_menu", ctx.lang),
                             reply_markup=CommonKBs.main_menu(ctx.lang))


class Assortment(StatesGroup):
    Menu = State()
    ViewingAssortment = State()
    ViewingProductDetails = State()
    FormingOrderEntry = State()
    EntryOptionSelect = State()
    ChoiceEditValue = State()
    SwitchesEditing = State()
    AdditionalsEditing = State()

@state_handlers.register(Assortment.Menu)
async def assortment_menu_handler(ctx: Context, **_):
    
    categories = await ctx.db.categories.get_all()
    if not categories:
        await call_state_handler(CommonStates.MainMenu, ctx, send_before="Err: There's no categroies!")
        return
    await ctx.message.answer(AssortmentTranslates.translate("choose_the_category", ctx.lang),
                             reply_markup=AssortmentKBs.assortment_menu(categories, ctx.lang))

@state_handlers.register(Assortment.ViewingAssortment)
async def viewing_assortment_handler(ctx: Context,
                                     category: str,
                                     current: int,
                                     **_):
    amount = await ctx.db.products.count_in_category(category)

    if amount == 0:
        await ctx.message.answer(AssortmentTranslates.translate("no_products_in_category", ctx.lang))
        await call_state_handler(Assortment.Menu,
                                 ctx)
        return
    
    # product: Product = await ctx.db.products.find_one_by({'order_no': current, "category": category})
    product: Product = await ctx.db.products.get_by_category_and_index(category, current-1)
    caption = AssortmentTextGen.generate_viewing_entry_caption(product,
                                                        ctx)

    await send_media_response(ctx.message,
                                product.short_description_photo_id,
                                caption,
                                AssortmentKBs.gen_assortment_view_kb(current, amount, ctx.lang))

@state_handlers.register(Assortment.ViewingProductDetails)
async def viewing_product_details_handler(ctx: Context,
                                          product: Product,
                                          **_):
    caption = AssortmentTextGen.generate_product_detailed_caption(product, ctx)

    # if ctx.is_query:
    #     await edit_media_message(ctx.message,
    #                             product.long_description_photo_id or product.long_description_video_id,
    #                             caption,
    #                             AssortmentKBs.detailed_view(ctx.lang),
    #                             "photo" if product.long_description_photo_id
    #                             else ("video" if product.long_description_video_id
    #                                 else None))
    # else:
    #     await clear_keyboard_effect(ctx.message)

    await send_media_response(ctx.message,
                                product.long_description_photo_id or product.long_description_video_id,
                                caption,
                                AssortmentKBs.detailed_view(ctx.lang)
                                )

@state_handlers.register(Assortment.FormingOrderEntry)
async def forming_order_entry_handler(ctx: Context,
                                      product: Product,
                                      **_):
    options: dict[str, ConfigurationOption] = product.configuration.options
    photo_id = product.configuration_photo_id
    video_id = product.configuration_video_id

    if ctx.is_query: await clear_keyboard_effect(ctx.message)
    
    additionals = await ctx.db.additionals.get(product)

    # if edit: await ctx.message.delete()
    await send_media_response(ctx.message,
                                photo_id or video_id,
                                AssortmentTextGen.generate_product_configurating_main(product, ctx),
                                AssortmentKBs.adding_to_cart_main(options, len(additionals) > 0, ctx.lang),
                                "photo" if photo_id else ("video" if video_id else None))

@state_handlers.register(Assortment.EntryOptionSelect)
async def entry_option_select_handler(ctx: Context,
                                      product: Product,
                                      delete_prev: bool = False,
                                      option: ConfigurationOption = None,
                                      **_):
    chosen = option.get_chosen()
    text = AssortmentTextGen.generate_choice_text(option, ctx.lang)
    kb = AssortmentKBs.generate_choice_kb(product, option, ctx)

    await send_media_response(ctx.message, chosen.photo_id or chosen.video_id, text, kb,
                              media_type="video" if chosen.video_id else "photo" if chosen.photo_id else "text")
    if delete_prev: await ctx.message.delete()

@state_handlers.register(Assortment.ChoiceEditValue)
async def choice_edit_value_handler(ctx: Context,
                                    choice,
                                    **_):
    await clear_keyboard_effect(ctx.message)

    text = AssortmentTextGen.generate_presets_text(ctx.lang) if choice.existing_presets else AssortmentTextGen.generate_custom_input_text(choice,
                                                                                                      ctx.lang)
    kb = UncategorizedKBs.inline_cancel(ctx.lang)

    await send_media_response(ctx.message,
                              choice.photo_id or choice.video_id,
                              text,
                              kb,
                              "photo" if choice.photo_id else ("video" if choice.video_id else None)
                              )

@state_handlers.register(Assortment.SwitchesEditing)
async def switches_editing_handler(ctx: Context,
                                   switches: ConfigurationSwitches,
                                   **_):

    text = AssortmentTextGen.generate_switches_text(switches, ctx)
    kb = AssortmentKBs.generate_switches_kb(switches, ctx.lang)

    await send_media_response(ctx.message,
                              switches.photo_id or switches.video_id,
                              text,
                              kb,
                              "photo" if switches.photo_id else ("video" if switches.video_id else None)
                              )

@state_handlers.register(Assortment.AdditionalsEditing)
async def additionals_editing_handler(ctx: Context,
                                   product: Product,
                                   allowed_additionals: List[ProductAdditional],
                                   **_):
    additionals = product.configuration.additionals

    text = AssortmentTextGen.generate_additionals_text(allowed_additionals, additionals, ctx.customer, ctx.lang)
    kb = AssortmentKBs.generate_additionals_kb(allowed_additionals, additionals, ctx.lang)

    if ctx.is_query: await ctx.message.delete()

    await ctx.message.answer(
        text,
        reply_markup=kb
    )

class Cart(StatesGroup):
    Menu = State()
    EntryRemoveConfirm = State()
    
    OrderConfigurationMenu = State()

@state_handlers.register(Cart.Menu)
async def cart_menu_handler(ctx: Context, current: int, **_):
    amount = await ctx.db.cart_entries.count_customer_cart_entries(ctx.customer)
    
    if amount == 0:
        await ctx.message.answer(CartTranslates.translate("no_products_in_cart", ctx.lang))
        await call_state_handler(CommonStates.MainMenu,
                                 ctx)
        return
    if current > amount: current = 1
    
    entry = await ctx.db.cart_entries.get_customer_cart_entry_by_id(ctx.customer, current-1)
    product: Product = await ctx.db.products.find_one_by_id(entry.product_id)
    
    caption = CartTextGen.generate_cart_viewing_caption(entry,
                                            product,
                                            entry.configuration,
                                            ctx)
    
    price = await ctx.db.cart_entries.calculate_customer_cart_price(ctx.customer)
    await send_media_response(ctx.message,
                            product.short_description_photo_id,
                            caption,
                            CartKBs.cart_view(entry, current, amount, price, ctx))

@state_handlers.register(Cart.EntryRemoveConfirm)
async def entry_remove_confirm_handler(ctx: Context, **_):
    await ctx.message.answer(CartTranslates.translate("entry_remove_confirm", ctx.lang),
                             reply_markup=UncategorizedKBs.yes_no(ctx.lang))

@state_handlers.register(Cart.OrderConfigurationMenu)
async def order_configuration_handler(ctx: Context, order: Order, **_):
    used_bonus_money: bool = bool(order.price_details.bonuses_applied)
    total_price = await ctx.db.cart_entries.calculate_customer_cart_price(ctx.customer)

    text = CartTextGen.generate_order_forming_caption(order, ctx)

    await ctx.message.answer(text,
                             reply_markup=CartKBs.cart_order_configuration(used_bonus_money, total_price, ctx))
  
class Profile(StatesGroup):
    Menu = State()
    
    class Settings(StatesGroup):
        Menu = State()
        ChangeLanguage = State()
        ChangeCurrency = State()
    class Delivery(StatesGroup):
        Menu = State()
        DeleteConfimation = State()
        
        class Editables(StatesGroup):
            IsForeign = State()
            Service = State()
            RequirementsLists = State()
            Requirement = State()

@state_handlers.register(Profile.Menu)
async def profile_menu_handler(ctx: Context, **_):
    await ctx.message.answer(ProfileTranslates.translate("menu", ctx.lang),
                             reply_markup=ProfileKBs.menu(ctx.lang))

@state_handlers.register(Profile.Settings.Menu)
async def settings_menu_handler(ctx: Context, **_):
    await ctx.message.answer(
        ProfileTextGen.settings_menu_text(ctx.lang),
        reply_markup=ProfileKBs.Settings.menu(ctx.lang)
    )

@state_handlers.register(Profile.Delivery.Menu)
async def delivery_menu_handler(ctx: Context, **_):
    await ctx.message.answer(
        ProfileTextGen.delivery_menu_text(ctx.customer.delivery_info, ctx),
        reply_markup=ProfileKBs.Delivery.menu(ctx.customer.delivery_info, ctx.lang)
    )
    
@state_handlers.register(Profile.Settings.ChangeLanguage)
async def settings_change_lang_handler(ctx: Context, **_):
    await ctx.message.answer(ProfileTranslates.Settings.translate("choose_lang", ctx.lang),
                             reply_markup=ProfileKBs.Settings.lang_choose(ctx.lang))
    
@state_handlers.register(Profile.Settings.ChangeCurrency)
async def settings_change_currency_handler(ctx: Context, **_):
    currency_name = UncategorizedTranslates.Currencies.translate(ctx.customer.currency, ctx.lang)
    await ctx.message.answer(ProfileTranslates.Settings.translate("choose_currency", ctx.lang).format(currency=currency_name),
                             reply_markup=ProfileKBs.Settings.currency_choose(ctx.lang))

@state_handlers.register(Profile.Delivery.Editables.IsForeign)
async def delivery_edit_is_foreign_handler(ctx: Context, **_):
    first_setup: bool = ctx.customer.delivery_info.service is None
    
    # serialized_service = await ctx.fsm.get_value("service")
    # service = DeliveryService(**serialized_service) if serialized_service else None
    
    await ctx.message.answer(
        ProfileTranslates.Delivery.translate("is_foreign_text", ctx.lang),
        reply_markup=ProfileKBs.Delivery.Editables.is_foreign(
            first_setup, ctx.lang
        )
    )
    
@state_handlers.register(Profile.Delivery.Editables.Service)
async def delivery_edit_service_handler(ctx: Context, **_):
    first_setup: bool = ctx.customer.delivery_info.service is None
    delivery_info = DeliveryInfo(**await ctx.fsm.get_value("delivery_info"))
    
    
    services = await ctx.db.delivery_services.get_all(delivery_info.is_foreign)
    
    await ctx.message.answer(
        ProfileTranslates.Delivery.translate("service_text", ctx.lang),
        reply_markup=ProfileKBs.Delivery.Editables.services(
            first_setup, services, ctx.customer, ctx.lang
        )
    )
    
@state_handlers.register(Profile.Delivery.Editables.RequirementsLists)
async def delivery_edit_requirements_lists_handler(ctx: Context, **_):
    first_setup: bool = ctx.customer.delivery_info.service is None
    delivery_info = DeliveryInfo(**await ctx.fsm.get_value("delivery_info"))
    
    
    lists = delivery_info.service.requirements_options
    
    await ctx.message.answer(
        ProfileTranslates.Delivery.translate("requirements_list_text", ctx.lang),
        reply_markup=ProfileKBs.Delivery.Editables.requirements_lists(
            first_setup, lists, ctx.lang
        )
    )

@state_handlers.register(Profile.Delivery.Editables.Requirement)
async def delivery_edit_requirement_handler(ctx: Context, **_):
    first_setup: bool = ctx.customer.delivery_info.service is None
    delivery_info: DeliveryInfo = DeliveryInfo(**await ctx.fsm.get_value("delivery_info"))
    requirement_index: int = await ctx.fsm.get_value("requirement_index")

    
    requirement = delivery_info.service.selected_option.requirements[requirement_index]
    
    await ctx.message.answer(
        ProfileTranslates.Delivery.translate("requirement_value_text", ctx.lang).format(name=requirement.name.get(ctx.lang), description=requirement.description.data.get(ctx.lang)),
        reply_markup=ProfileKBs.Delivery.Editables.requirement(
            first_setup, ctx.lang
        )
    )

@state_handlers.register(Profile.Delivery.DeleteConfimation)
async def delivery_delete_confirmation_handler(ctx: Context, **_):
    await ctx.message.answer(
        ProfileTranslates.Delivery.translate("delete_confimation", ctx.lang),
        reply_markup=ProfileKBs.Delivery.delete_confimation(
            ctx.lang
        )
    )