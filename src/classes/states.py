from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery
from typing import Callable, Dict, Any, Awaitable

from src.classes.helper_classes import Context
from src.classes.message_tools import clear_keyboard_effect, edit_media_message, send_media_response
from src.classes.texts import generate_additionals_text, generate_choice_text, generate_custom_input_text, generate_presets_text, \
    generate_product_configurating_main, generate_product_detailed_caption, generate_switches_text, \
    generate_viewing_assortment_entry_caption
from src.classes.keyboards import *
from src.classes.translates import AssortmentTranslates, CommonTranslates


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
                             change_state=True,
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
        await handler(ctx=ctx, **kwargs)

    except Exception as e:
        await ctx.message.answer(f"Error: {e}")
        await ctx.message.delete()
        if state != CommonStates.main_menu:
            await call_state_handler(CommonStates.main_menu, ctx)
        raise e


class CommonStates(StatesGroup):
    lang_choosing = State()
    currency_choosing = State()
    main_menu = State()


@state_handlers.register(CommonStates.lang_choosing)
async def handle_lang_choosing(ctx: Context, **_):
    await ctx.message.answer("Выберите язык:\n\nChoose language:",
                             reply_markup=CommonKBs.lang_choose())


@state_handlers.register(CommonStates.currency_choosing)
async def handle_currency_choosing(ctx: Context, **_):
    await ctx.message.answer(CommonTranslates.translate("currency_choosing", ctx.lang),
                             reply_markup=CommonKBs.currency_choose())


@state_handlers.register(CommonStates.main_menu)
async def main_menu_handler(ctx: Context, **_):
    await ctx.message.answer(CommonTranslates.translate("heres_the_menu", ctx.lang),
                             reply_markup=CommonKBs.main_menu(ctx.lang))


class MainMenuOptions(StatesGroup):
    Assortment = State()
    Cart = State()
    Orders = State()


@state_handlers.register(MainMenuOptions.Assortment)
async def assortment_menu_handler(ctx: Context, **_):
    await ctx.message.answer(AssortmentTranslates.translate("choose_the_category", ctx.lang),
                             reply_markup=await AssortmentKBs.assortment_menu(ctx.db, ctx.lang))
    if isinstance(ctx.event, CallbackQuery):
        await ctx.message.delete()
        await ctx.fsm.set_data({})


class Assortment(StatesGroup):
    ViewingAssortment = State()
    ViewingProductDetails = State()
    FormingOrderEntry = State()
    EntryOptionSelect = State()
    ChoiceEditValue = State()
    SwitchesEditing = State()
    AdditionalsEditing = State()


@state_handlers.register(Assortment.ViewingAssortment)
async def viewing_assortment_handler(ctx: Context,
                                     edit: bool,
                                     category: str,
                                     current: int,
                                     amount: int,
                                     **_):
    if amount == 0:
        await ctx.message.answer(AssortmentTranslates.translate("no_products_in_category", ctx.lang))
        await call_state_handler(MainMenuOptions.Assortment,
                                 ctx)
        return

    product: Product = await ctx.db.products.find_one_by({'order_no': current, "category": category})
    caption = generate_viewing_assortment_entry_caption(product,
                                                        ctx.customer.balance,
                                                        ctx.lang)

    if edit:
        await edit_media_message(ctx.message,
                                 product.short_description_photo_id,
                                 caption,
                                 AssortmentKBs.gen_assortment_view_kb(current, amount, ctx.lang))
    else:
        await clear_keyboard_effect(ctx.message)
        await send_media_response(ctx.message,
                                  product.short_description_photo_id,
                                  caption,
                                  AssortmentKBs.gen_assortment_view_kb(current, amount, ctx.lang))

        await ctx.fsm.set_data({})

    await ctx.fsm.update_data(current=current, category=category, amount=amount)


@state_handlers.register(Assortment.ViewingProductDetails)
async def viewing_product_details_handler(ctx: Context,
                                          product: Product,
                                          **_):
    caption = generate_product_detailed_caption(product, ctx.customer.balance, ctx.lang)

    # if edit:
    await edit_media_message(ctx.message,
                             product.long_description_photo_id or product.long_description_video_id,
                             caption,
                             AssortmentKBs.detailed_view(ctx.lang),
                             "photo" if product.long_description_photo_id
                             else ("video" if product.long_description_video_id
                                   else None))
    # else:
    #     await ctx.message.delete()

    #     await send_media_response(ctx.message,
    #                               product.long_description_photo_id,
    #                               caption,
    #                               AssortmentKBs.detailed_view(ctx.lang)
    #                               )

    #     await ctx.fsm.update_data(product=None)


@state_handlers.register(Assortment.FormingOrderEntry)
async def forming_order_entry_handler(ctx: Context,
                                      edit: bool,
                                      product: Product):
    options: dict[str, ConfigurationOption] = product.configuration.options
    photo_id = product.configuration_photo_id
    video_id = product.configuration_video_id

    if not isinstance(ctx.event, CallbackQuery): await clear_keyboard_effect(ctx.message)

    await ctx.fsm.update_data(product=product.model_dump())

    additionals = await ctx.db.additionals.get(product.category, product.id)

    if edit:
        await edit_media_message(ctx.message,
                                 photo_id or video_id,
                                 generate_product_configurating_main(product, ctx.lang, ctx.customer.balance),
                                 AssortmentKBs.adding_to_cart_main(options, len(additionals) > 0, ctx.lang),
                                 "photo" if photo_id else ("video" if video_id else None))
    else:
        await send_media_response(ctx.message,
                                  photo_id or video_id,
                                  generate_product_configurating_main(product, ctx.lang, ctx.customer.balance),
                                  AssortmentKBs.adding_to_cart_main(options, len(additionals) > 0, ctx.lang),
                                  "photo" if photo_id else ("video" if video_id else None))


@state_handlers.register(Assortment.EntryOptionSelect)
async def entry_option_select_handler(ctx: Context,
                                      delete_prev: bool,
                                      option: ConfigurationOption,
                                      idx: int = None):
    chosen = option.get_chosen()
    text = generate_choice_text(option, ctx.lang)
    kb = AssortmentKBs.generate_choice_kb(option, ctx.lang)

    await send_media_response(ctx.message, chosen.photo_id or chosen.video_id, text, kb,
                              media_type="video" if chosen.video_id else "photo" if chosen.photo_id else "text")
    if delete_prev: await ctx.message.delete()

    await ctx.fsm.update_data(changing_option=option.model_dump())
    
    # \/\/\/\/\/\/\/\/ ВАЖНО, тк 0 == False
    if idx is not None: await ctx.fsm.update_data(current_option_idx=idx)


@state_handlers.register(Assortment.ChoiceEditValue)
async def choice_edit_value_handler(ctx: Context,
                                    changing_option: ConfigurationOption,
                                    choice):
    await ctx.fsm.update_data(before_option=changing_option.model_dump())
    
    changing_option.set_chosen(choice)

    await clear_keyboard_effect(ctx.message)

    text = generate_presets_text(ctx.lang) if choice.existing_presets else generate_custom_input_text(choice,
                                                                                                      ctx.lang)
    kb = UncategorizedKBs.inline_cancel(ctx.lang)

    await send_media_response(ctx.message,
                              choice.photo_id or choice.video_id,
                              text,
                              kb,
                              "photo" if choice.photo_id else ("video" if choice.video_id else None)
                              )

    await ctx.fsm.update_data(changing_option=changing_option.model_dump())


@state_handlers.register(Assortment.SwitchesEditing)
async def switches_editing_handler(ctx: Context,
                                   switches: ConfigurationSwitches,
                                   switch_text: str = None):
    # if not switch_text: await clear_keyboard_effect(ctx.message)
    if switch_text:
        clean_text = switch_text.replace(" ✅", "")
        for idx, switch in enumerate(switches.switches):
            if switch.name.data[ctx.lang] == clean_text:
                switches.switches[idx].enabled = not switch.enabled
                break 
        
        product = Product(**await ctx.fsm.get_value("product"))
        current_option_idx = await ctx.fsm.get_value("current_option_idx")

        option = product.configuration.options[current_option_idx] # ссылка на текущую изменяемую главную опцию
        idx = option.get_index_by_label(switches.label.data[ctx.lang], ctx.lang)
        option.choices[idx] = switches

        await ctx.fsm.update_data(product=product.model_dump())
        await ctx.fsm.update_data(changing_option=option.model_dump())

    text = generate_switches_text(switches, ctx.customer.balance, ctx.lang)
    kb = AssortmentKBs.generate_switches_kb(switches, ctx.lang)

    await send_media_response(ctx.message,
                              switches.photo_id or switches.video_id,
                              text,
                              kb,
                              "photo" if switches.photo_id else ("video" if switches.video_id else None)
                              )

    await ctx.fsm.update_data(switches=switches.model_dump())

@state_handlers.register(Assortment.AdditionalsEditing)
async def additionals_editing_handler(ctx: Context,
                                   product: Product,
                                   additional_text: str = None):
    
    allowed_additionals = await ctx.db.additionals.get(product.category, product.id)
    additionals = product.configuration.additionals
    
    if additional_text:
        additional_text = ctx.message.text.replace(" ✅", "")
        additional = ctx.db.additionals.get_by_name(additional_text, allowed_additionals, ctx.lang)

        if additional in additionals:
            additionals.remove(additional)
        else:
            additionals.append(additional)
            
        
        await ctx.fsm.update_data(product=product.model_dump())

    text = generate_additionals_text(allowed_additionals, additionals, ctx.customer.balance, ctx.lang)
    kb = AssortmentKBs.generate_additionals_kb(allowed_additionals, additionals, ctx.lang)

    if isinstance(ctx.event, CallbackQuery): await ctx.message.delete()

    await ctx.message.answer(
        text,
        reply_markup=kb
    )