import logging
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardRemove
from typing import Callable, Dict, Any, Awaitable, Tuple, Union, List

from ui.message_tools import clear_keyboard_effect, send_media_response
from ui.texts import *
from ui.keyboards import *


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
                await ctx.message.answer(send_before, reply_markup=ReplyKeyboardRemove())
            elif isinstance(send_before, tuple):
                text, sleep_time = send_before
                
                await ctx.message.answer(text, reply_markup=ReplyKeyboardRemove())
                cached_state = await ctx.fsm.get_state()
                await ctx.fsm.set_state("nothing")
                
                await asyncio.sleep(sleep_time)
                
                await ctx.fsm.set_state(cached_state)
            
        await handler(ctx=ctx, **kwargs)

    except Exception as e:
        logging.getLogger(__name__).exception(f"Error in state handler: {e}")
        await ctx.message.answer(f"Error: {e}")
        await ctx.services.notificators.TelegramChannelLogs.send_error(ctx, e)
            
        
        if state != CommonStates.MainMenu:
            await call_state_handler(CommonStates.MainMenu, ctx)
        raise e
    
    
class AdminStates(StatesGroup):
    
    class Main(StatesGroup):
        Menu = State()
        
        class Customers(StatesGroup):
            AskId = State()
            CustomerMenu = State()
            
        class Orders(StatesGroup):
            AskId = State()
            OrderMenu = State()
            
            ChangeStatusChoice = State()
            SetChangeStatusComment = State()
            
        class DiscountedProducts(StatesGroup):
            Menu = State()
            Creating = State()
            AskDeleteId = State()
            
            EditAskId = State()
            Edit = State()
        
        class Promocodes(StatesGroup):
            Menu = State()
            Creating = State()
            
        class Statistics(StatesGroup):
            Menu = State()
        
        class GlobalPlaceholders(StatesGroup):
            Menu = State()
            CreatingKey = State()
            CreatingLangs = State()
            EditKey = State()
            EditLangs = State()
    
    class Commands(StatesGroup):
        Console = State()
    
    class Customers(StatesGroup):
        AdminMessageSending = State()
    
    class Order(StatesGroup):
        PriceConfirmationWaiting = State()
        
        UnformAskForComment = State()
    
    class Delivery(StatesGroup):
        PriceConfirmationCancel = State()
        
@state_handlers.register(AdminStates.Main.Menu)
async def handle_admin_menu(ctx: Context, **_):
    await ctx.message.answer("Выберите пункт меню:",
                             reply_markup=AdminKBs.admin_menu())

@state_handlers.register(AdminStates.Main.Customers.AskId)
async def handle_admin_customers_ask_id(ctx: Context, **_):
    await ctx.message.answer("Введите ID пользователя:", reply_markup=UncategorizedKBs.reply_cancel(ctx))
    
@state_handlers.register(AdminStates.Main.Customers.CustomerMenu)
async def handle_admin_customers_menu(ctx: Context, customer: Customer, **_):
    await ctx.message.answer(await AdminTextGen.customer_menu_text(customer, ctx), 
                             reply_markup=AdminKBs.Customers.customer_menu(customer, ctx))
    
@state_handlers.register(AdminStates.Main.Orders.AskId)
async def handle_admin_orders_ask_id(ctx: Context, **_):
    await ctx.message.answer(await AdminTextGen.active_orders_menu_text(ctx))
    await ctx.message.answer("Введите ID заказа либо попытайтесь найти по PUIDу (начинать с #):", reply_markup=AdminKBs.Orders.orders_menu(ctx))
    
@state_handlers.register(AdminStates.Main.Orders.OrderMenu)
async def handle_admin_orders_menu(ctx: Context, order: Order, **_):
    cart_entries = await ctx.services.db.cart_entries.find_entries_by_order(order)
    
    imgs = []

    for entry in cart_entries:
        for option_name in ('size', 'color', 'firmness'):
            if (entry.configuration and 
                (option := entry.configuration.options.get(option_name)) and
                (chosen := option.get_chosen()) and 
                chosen.media):
                imgs.append(chosen.media)
        
        if (entry.source_type == CartItemSource.discounted and 
            entry.frozen_snapshot):
            imgs.append(entry.frozen_snapshot.media)
            
    for img in imgs:
        await send_media_response(ctx, img)
        await asyncio.sleep(0.3)
    await ctx.message.answer(await AdminTextGen.order_menu_text(order, ctx),
                             reply_markup=AdminKBs.Orders.order_menu(ctx))
    
@state_handlers.register(AdminStates.Main.Orders.ChangeStatusChoice)
async def handle_admin_orders_change_status_choice(ctx: Context, **_):
    await ctx.message.answer("Выберите новый статус:", reply_markup=AdminKBs.Orders.change_status_choice(ctx))
    
@state_handlers.register(AdminStates.Main.Orders.SetChangeStatusComment)
async def handle_admin_orders_set_change_status_comment(ctx: Context, **_):
    await ctx.message.answer("Введите комментарий (если не надо - введите ноль):", reply_markup=UncategorizedKBs.reply_cancel(ctx))

@state_handlers.register(AdminStates.Main.DiscountedProducts.Menu)
async def handle_admin_discounted_products(ctx: Context, **_):
    await ctx.message.answer("Выберите пункт меню:",
                             reply_markup=AdminKBs.DiscountedProducts.admin_discounted_products_menu(ctx))

@state_handlers.register(AdminStates.Main.DiscountedProducts.Creating)
async def handle_admin_create_discounted_product(ctx: Context, **_):
    txt = """Имя_товара:
  ru: тут на русском кратко, но чтобы было понятно кто что
  en: here in english
Цена: обязательно формата — "USD:100;RUB:1200"
Ключ_медиа: спроси у меня в лс
Описание_что_не_так_и_тп:
  ru: Здесь там-то и то-то не так
  en: Here that and this is wrong

<code>Имя_товара:
  ru:
  en:
Цена: USD:70;RUB:5000
Ключ_медиа:
Описание_что_не_так_и_тп:
  ru:
  en:</code>

Введите ОБЯЗАТЕЛЬНО все поля по шаблону:"""
    await ctx.message.answer(txt, reply_markup=UncategorizedKBs.reply_cancel(ctx))

@state_handlers.register(AdminStates.Main.DiscountedProducts.EditAskId)
async def handle_admin_discounted_products_ask_edit_id(ctx: Context, **_):
    await ctx.message.answer("Введите ID для редактирования:", reply_markup=UncategorizedKBs.reply_cancel(ctx))

@state_handlers.register(AdminStates.Main.DiscountedProducts.Edit)
async def handle_admin_edit_discounted_product(ctx: Context, discounted_product: DiscountedProduct, **_):
    txt = f"""<code>Имя_товара:
  ru: {discounted_product.name.get("ru")}
  en: {discounted_product.name.get("en")}
Цена: {';'.join([f'{c}:{p.amount}' for c, p in discounted_product.price.data.items()])}
Ключ_медиа: {discounted_product.media.media_key}
Описание_что_не_так_и_тп:
  ru: {discounted_product.description.get("ru")}
  en: {discounted_product.description.get("en")}</code>

Введите ОБЯЗАТЕЛЬНО все поля по шаблону:"""
    await ctx.message.answer(txt, reply_markup=UncategorizedKBs.reply_cancel(ctx))
    
@state_handlers.register(AdminStates.Main.DiscountedProducts.AskDeleteId)
async def handle_admin_discounted_products_ask_delete_id(ctx: Context, **_):
    await ctx.message.answer("Введите ID для удаления:", reply_markup=UncategorizedKBs.reply_cancel(ctx))

@state_handlers.register(AdminStates.Main.Promocodes.Menu)
async def handle_admin_promocodes(ctx: Context, **_):
    await ctx.message.answer("Выберите пункт меню:",
                             reply_markup=AdminKBs.Promocodes.admin_promocodes_menu(ctx))

@state_handlers.register(AdminStates.Main.Promocodes.Creating)
async def handle_admin_create_promocode(ctx: Context, **_):
    txt = """Код:
Тип: percent | fixed
Значение: для percent — просто число 10 (-> 10%), для fixed — "USD:100;RUB:1200"
Описание:
  ru: Скидка 10% для новых клиентов
  en: 10% discount for new customers
Только_новички: yes | no
Макс_использований: -1 — без ограничений
Разрешенные_чойсы: 0 — если не надо, а так option_name/choice_name через запятую без пробелов
Expire: 2025-12-31    # YYYY-MM-DD или 30d (только в днях) или none

<code>Код:
Тип:
Значение:
Описание:
  ru:
  en:
Только_новички: no
Макс_использований: -1
Разрешенные_чойсы: 0
Expire: 30d</code>

Введите ОБЯЗАТЕЛЬНО все поля по шаблону:"""
    await ctx.message.answer(txt, reply_markup=UncategorizedKBs.reply_cancel(ctx))

@state_handlers.register(AdminStates.Main.Statistics.Menu)
async def handle_admin_promocodes(ctx: Context, **_):
    await ctx.message.answer("Выберите пункт статистики:",
                             reply_markup=AdminKBs.Statistics.admin_statistics_menu(ctx))

@state_handlers.register(AdminStates.Main.GlobalPlaceholders.Menu)
async def handle_admin_global_placeholders(ctx: Context, **_):
    await ctx.message.answer("Выберите пункт меню:",
                             reply_markup=AdminKBs.GlobalPlaceholders.admin_global_placeholders_menu(ctx))

@state_handlers.register(AdminStates.Main.GlobalPlaceholders.CreatingKey)
async def handle_admin_create_global_placeholder(ctx: Context, **_):
    await ctx.message.answer("Введите ключ:", reply_markup=UncategorizedKBs.reply_cancel(ctx))

@state_handlers.register(AdminStates.Main.GlobalPlaceholders.CreatingLangs)
async def handle_admin_create_global_placeholder_langs(ctx: Context, **_):
    for lang in SUPPORTED_LANGUAGES_TEXT.values():
        if not await ctx.fsm.get_value(lang):
            await ctx.message.answer(f"Введите значение для языка {lang}:", reply_markup=UncategorizedKBs.reply_cancel(ctx))
            return

@state_handlers.register(AdminStates.Main.GlobalPlaceholders.EditKey)
async def handle_admin_edit_global_placeholder_request_key(ctx: Context, **_):
    await ctx.message.answer("Введите ключ:", reply_markup=UncategorizedKBs.reply_cancel(ctx))

@state_handlers.register(AdminStates.Main.GlobalPlaceholders.EditLangs)
async def handle_admin_edit_global_placeholder(ctx: Context, placeholder: Placeholder, **_):
    for lang in SUPPORTED_LANGUAGES_TEXT.values():
        if not await ctx.fsm.get_value(lang):
            await ctx.message.answer(f"Было: {placeholder.value.get(lang)}\nВведите новое значение для языка {lang}:", reply_markup=UncategorizedKBs.reply_cancel(ctx))
            return

@state_handlers.register(AdminStates.Commands.Console)
async def handle_code_execution_entry_point_message(ctx: Context, **_):
    await ctx.message.answer("Введите 0 если хотите выйти:")

@state_handlers.register(AdminStates.Customers.AdminMessageSending)
async def handle_admin_message_sending(ctx: Context, **_):
    await ctx.message.answer("Введите сообщение:", reply_markup=UncategorizedKBs.reply_cancel(ctx))
    
@state_handlers.register(AdminStates.Order.PriceConfirmationWaiting)
async def handle_price_confirmation_waiting(ctx: Context, entries: Iterable[CartEntry], **_):
    text = AdminTextGen.price_confirmation_text(list(entries), ctx)
    await ctx.message.answer(text, reply_markup=UncategorizedKBs.reply_cancel(ctx))

@state_handlers.register(AdminStates.Order.UnformAskForComment)
async def handle_unform_ask_for_comment(ctx: Context, customer: Customer, **_):
    await ctx.message.answer(f"Если хотите отменить заказ с комментарием, введите его следующим сообщением. (Язык пользователя - {customer.lang})\nХотите без комментария, отправьте 0",
                             reply_markup=UncategorizedKBs.reply_cancel(ctx))
    
@state_handlers.register(AdminStates.Delivery.PriceConfirmationCancel)
async def handle_price_confirmation_cancel(ctx: Context, customer: Customer, **_):
    await ctx.message.answer(f"Если хотите отменить доставку с комментарием, введите его следующим сообщением. (Язык пользователя - {customer.lang})\nХотите без комментария, отправьте 0",
                             reply_markup=UncategorizedKBs.reply_cancel(ctx))
    
class NewUserStates(StatesGroup):
    LangChoosing = State()
    AskAge = State()
    CurrencyChoosing = State()

@state_handlers.register(NewUserStates.LangChoosing)
async def handle_lang_choosing(ctx: Context, **_):
    await ctx.message.answer("Выберите язык:\n\nChoose language:",
                             reply_markup=CommonKBs.lang_choose())
    
@state_handlers.register(NewUserStates.AskAge)
async def handle_ask_age(ctx: Context, **_):
    await ctx.message.answer(ctx.t.CommonTranslates.maturity_question,
                             reply_markup=UncategorizedKBs.inline_yes_no(ctx))

@state_handlers.register(NewUserStates.CurrencyChoosing)
async def handle_currency_choosing(ctx: Context, **_):
    await ctx.message.answer(ctx.t.CommonTranslates.currency_choosing,
                             reply_markup=CommonKBs.currency_choose(ctx))

class CommonStates(StatesGroup):
    MainMenu = State()

@state_handlers.register(CommonStates.MainMenu)
async def main_menu_handler(ctx: Context, **_):
    await ctx.message.answer(ctx.t.CommonTranslates.heres_the_menu,
                             reply_markup=CommonKBs.main_menu(ctx))


class AssortmentStates(StatesGroup):
    Menu = State()
    ViewingAssortment = State()
    ViewingProductDetails = State() # DEPRECATED
    FormingOrderEntry = State()
    EntryOptionSelect = State()
    ChoiceEditValue = State()
    SwitchesEditing = State()
    AdditionalsEditing = State()

@state_handlers.register(AssortmentStates.Menu)
async def assortment_menu_handler(ctx: Context, **_):
    categories = await ctx.services.db.categories.get_all()
    if not categories:
        await call_state_handler(CommonStates.MainMenu, ctx, send_before="Err: There's no categories!")
        return
    await ctx.message.answer(ctx.t.AssortmentTranslates.choose_the_category,
                             reply_markup=AssortmentKBs.assortment_menu(categories, ctx))

@state_handlers.register(AssortmentStates.ViewingAssortment)
async def viewing_assortment_handler(ctx: Context,
                                     category: str,
                                     current: int,
                                     **_):
    amount = await ctx.services.db.products.count_in_category(category, only_visible=True)

    if amount == 0:
        await call_state_handler(AssortmentStates.Menu,
                                 ctx, send_before=(ctx.t.AssortmentTranslates.no_products_in_category, 0.2))
        return
    
    product: Product = await ctx.services.db.products.find_by_category_and_index(category, current-1, only_visible=True)
    if not product:
        await call_state_handler(AssortmentStates.ViewingAssortment,
                                 ctx, 
                                 category=category, 
                                 current=0)
        return
    caption = AssortmentTextGen.generate_viewing_entry_caption(product,
                                                        ctx)

    await send_media_response(ctx,
                                product.description_media,
                                caption,
                                AssortmentKBs.gen_assortment_view_kb(current, amount, ctx))

@state_handlers.register(AssortmentStates.FormingOrderEntry)
async def forming_order_entry_handler(ctx: Context,
                                      product: Product,
                                      annotation: ConfigurationAnnotation = None,
                                      **_):
    

    options: list[ConfigurationOption] = list(product.configuration.get_options(only_options=False).values())

    if ctx.is_query: await clear_keyboard_effect(ctx.message)
    
    additionals = await ctx.services.db.additionals.get(product)
    
    kb = AssortmentKBs.adding_to_cart_main(options, len(additionals) > 0, ctx)
    
    if annotation:
        await send_media_response(ctx, annotation.media, annotation.text.get(ctx), kb)
        return

    await send_media_response(ctx,
                            product.configuration_media,
                            AssortmentTextGen.generate_product_configurating_main(product, ctx),
                            kb)

@state_handlers.register(AssortmentStates.EntryOptionSelect)
async def entry_option_select_handler(ctx: Context,
                                      product: Product,
                                      delete_prev: bool = False,
                                      option: ConfigurationOption = None,
                                      annotation: ConfigurationAnnotation = None,
                                      **_):
    chosen = option.get_chosen()
    text = AssortmentTextGen.generate_choice_text(option, ctx)
    kb = AssortmentKBs.generate_choice_kb(product, option, ctx)
    
    if annotation:
        await send_media_response(ctx, annotation.media, annotation.text.get(ctx), kb)
        return
    
    await send_media_response(ctx, chosen.media, text, kb)
    if delete_prev: await ctx.message.delete()

@state_handlers.register(AssortmentStates.ChoiceEditValue)
async def choice_edit_value_handler(ctx: Context,
                                    choice: ConfigurationChoice,
                                    **_):
    await clear_keyboard_effect(ctx.message)

    text = AssortmentTextGen.generate_presets_text(ctx) if choice.existing_presets else AssortmentTextGen.generate_custom_input_text(choice, ctx)
    kb = UncategorizedKBs.inline_cancel(ctx)
    

    await send_media_response(ctx,
                              choice.media,
                              text,
                              kb)

@state_handlers.register(AssortmentStates.SwitchesEditing)
async def switches_editing_handler(ctx: Context,
                                   switches: ConfigurationSwitches,
                                   configuration: ProductConfiguration,
                                   **_):

    text = AssortmentTextGen.generate_switches_text(switches, ctx)
    kb = AssortmentKBs.generate_switches_kb(configuration, switches, ctx)

    await send_media_response(ctx,
                              switches.media,
                              text,
                              kb)

@state_handlers.register(AssortmentStates.AdditionalsEditing)
async def additionals_editing_handler(ctx: Context,
                                   product: Product,
                                   allowed_additionals: List[ProductAdditional],
                                   **_):
    additionals = product.configuration.additionals

    text = AssortmentTextGen.generate_additionals_text(allowed_additionals, additionals, ctx)
    kb = AssortmentKBs.generate_additionals_kb(allowed_additionals, additionals, ctx)

    if ctx.is_query: await ctx.message.delete()

    await ctx.message.answer(
        text,
        reply_markup=kb
    )
    
class DiscountedStates(StatesGroup):
    ViewingProducts = State()
    
@state_handlers.register(DiscountedStates.ViewingProducts)
async def viewing_products_handler(ctx: Context,
                                   current: int, 
                                   **_):
    amount = await ctx.services.db.discounted_products.count()
    
    if amount == 0:
        await call_state_handler(CommonStates.MainMenu,
                                 ctx, send_before=(ctx.t.DiscountedProductsTranslates.no_discounted_products, 1))
        return
    
    discounted_product: DiscountedProduct = await ctx.services.db.discounted_products.find_by_index(current-1)
    caption = DiscountedProductsGen.generate_discounted_product_text(discounted_product, ctx)
    
    await send_media_response(ctx,
                            discounted_product.media,
                            caption,
                            DiscountedProductKBs.gen_discounted_product_view(current, amount, ctx))

class CartStates(StatesGroup):
    Menu = State()
    EntryRemoveConfirm = State()
    CartPriceConfirmation = State()
    
    class OrderConfiguration(StatesGroup):
        Menu = State()
        PromocodeSetting = State()
        PaymentMethodSetting = State()
        PaymentConfirmation = State()

@state_handlers.register(CartStates.Menu)
async def cart_menu_handler(ctx: Context, current: int = 1, **_):
    amount = await ctx.services.db.cart_entries.count_customer_cart_entries(ctx.customer)
    
    if amount == 0:
        await call_state_handler(CommonStates.MainMenu,
                                 ctx, send_before=(ctx.t.CartTranslates.no_products_in_cart, 1))
        return
    if current > amount: current = 1
    
    entry = await ctx.services.db.cart_entries.find_customer_cart_entry_by_id(ctx.customer, current-1)
    is_product = entry.source_type == CartItemSource.product
    
    product: Product = await ctx.services.db.products.find_one_by_id(entry.source_id) if is_product else None
    total_price = await ctx.services.db.cart_entries.calculate_customer_cart_price(ctx.customer)
    
    caption = CartTextGen.generate_cart_viewing_caption(entry=entry,
                                            product=product,
                                            ctx=ctx)
    
    await send_media_response(ctx,
                            product.description_media if is_product else entry.frozen_snapshot.media,
                            caption,
                            await CartKBs.cart_view(entry, current, amount, total_price, ctx))

@state_handlers.register(CartStates.EntryRemoveConfirm)
async def entry_remove_confirm_handler(ctx: Context, **_):
    await ctx.message.answer(ctx.t.CartTranslates.entry_remove_confirm,
                             reply_markup=UncategorizedKBs.yes_no(ctx))

@state_handlers.register(CartStates.CartPriceConfirmation)
async def order_price_confirmation_handler(ctx: Context, order: Order, **_):
    await ctx.message.answer(await CartTextGen.generate_cart_price_confirmation_caption(order, ctx),
                             reply_markup=CartKBs.cart_price_confirmation(ctx))

@state_handlers.register(CartStates.OrderConfiguration.Menu)
async def order_configuration_handler(ctx: Context, order: Order, **_):
    await ctx.message.answer(await CartTextGen.generate_order_forming_caption(order, ctx),
                             reply_markup=CartKBs.cart_order_configuration(order, ctx))

@state_handlers.register(CartStates.OrderConfiguration.PromocodeSetting)
async def order_promocode_setting_handler(ctx: Context, **_):
    await ctx.message.answer(ctx.t.CartTranslates.OrderConfiguration.enter_promocode,
                             reply_markup=UncategorizedKBs.reply_back(ctx))
    
@state_handlers.register(CartStates.OrderConfiguration.PaymentMethodSetting)
async def order_payment_method_setting_handler(ctx: Context, order: Order, **_):
    await ctx.message.answer(CartTextGen.generate_payment_method_setting_caption(order, ctx),
                             reply_markup=CartKBs.payment_method_choose(order, ctx))
    
@state_handlers.register(CartStates.OrderConfiguration.PaymentConfirmation)
async def order_payment_confirmation_handler(ctx: Context, order: Order, **_):
    await ctx.message.answer(CartTextGen.generate_payment_confirmation_caption(order, ctx),
                             reply_markup=CartKBs.payment_confirmation(order, ctx))

class OrderStates(StatesGroup):
    Menu = State()
    OrderView = State()
    
@state_handlers.register(OrderStates.Menu)
async def orders_menu_handler(ctx: Context, **_):
    orders = await ctx.services.db.orders.find_customer_orders(ctx.customer)

    await ctx.message.answer(await OrdersTextGen.generate_orders_menu_text(orders, ctx),
                             reply_markup=UncategorizedKBs.reply_back(ctx))
    
@state_handlers.register(OrderStates.OrderView)
async def order_view_handler(ctx: Context, order: Order, **_):
    await ctx.message.answer(await OrdersTextGen.generate_order_viewing_caption(order, ctx),
                             reply_markup=OrdersKBs.order_view(order, ctx))

class ProfileStates(StatesGroup):
    Menu = State()
    class Settings(StatesGroup):
        Menu = State()
        ChangeLanguage = State()
        ChangeCurrency = State()
    class Referrals(StatesGroup):
        AskForJoin = State()
        Menu = State()
        
        InvitationLinkView = State()
    class Delivery(StatesGroup):
        Menu = State()
        DeleteConfimation = State()
        class Editables(StatesGroup):
            IsForeign = State()
            Service = State()
            RequirementsLists = State()
            Requirement = State()
            SendToManualConfirmation = State()

@state_handlers.register(ProfileStates.Menu)
async def profile_menu_handler(ctx: Context, **_):
    await ctx.message.answer(ctx.t.ProfileTranslates.menu,
                             reply_markup=ProfileKBs.menu(ctx))

@state_handlers.register(ProfileStates.Settings.Menu)
async def settings_menu_handler(ctx: Context, **_):
    await ctx.message.answer(
        ctx.t.ProfileTranslates.Settings.menu,
        reply_markup=ProfileKBs.Settings.menu(ctx) 
    )

@state_handlers.register(ProfileStates.Settings.ChangeLanguage)
async def settings_change_lang_handler(ctx: Context, **_):
    await ctx.message.answer(ctx.t.ProfileTranslates.Settings.choose_lang,
                             reply_markup=ProfileKBs.Settings.lang_choose(ctx))
    
@state_handlers.register(ProfileStates.Settings.ChangeCurrency)
async def settings_change_currency_handler(ctx: Context, **_):
    currency_name = getattr(ctx.t.UncategorizedTranslates.Currencies, ctx.customer.currency)
    await ctx.message.answer(ctx.t.ProfileTranslates.Settings.choose_currency.format(currency=currency_name),
                             reply_markup=ProfileKBs.Settings.currency_choose(ctx))

@state_handlers.register(ProfileStates.Referrals.AskForJoin)
async def refferals_ask_for_join_handler(ctx: Context, **_):
    await ctx.message.answer(
        ctx.t.ProfileTranslates.Referrals.ask_for_join,
        reply_markup=ProfileKBs.Referrals.ask_for_join(ctx)
    )

@state_handlers.register(ProfileStates.Referrals.Menu)
async def refferals_menu_handler(ctx: Context, inviter: Inviter, **_):
    await ctx.message.answer(
        ProfileTextGen.referrals_menu_text(inviter, ctx),
        reply_markup=ProfileKBs.Referrals.menu(ctx)
    )
    
@state_handlers.register(ProfileStates.Referrals.InvitationLinkView)
async def referrals_invitation_link_view_handler(ctx: Context, inviter: Inviter, **_):
    await ctx.message.answer(
        await ProfileTextGen.referrals_invitation_link_view_text(inviter, ctx)
    )
    
    await ctx.message.answer(
        await ProfileTextGen.hidden_invitation_link(inviter, ctx),
        reply_markup=UncategorizedKBs.reply_back(ctx)
    )

@state_handlers.register(ProfileStates.Delivery.Menu)
async def delivery_menu_handler(ctx: Context, **_):
    await ctx.message.answer(
        ProfileTextGen.delivery_menu_text(ctx.customer.privacy_data.delivery_info, ctx),
        reply_markup=ProfileKBs.Delivery.menu(ctx.customer.privacy_data.delivery_info, ctx)
    )

@state_handlers.register(ProfileStates.Delivery.Editables.IsForeign)
async def delivery_edit_is_foreign_handler(ctx: Context, **_):
    first_setup: bool = ctx.customer.privacy_data.delivery_info.service is None
    
    await ctx.message.answer(
        ctx.t.ProfileTranslates.Delivery.is_foreign_text,
        reply_markup=ProfileKBs.Delivery.Editables.is_foreign(
            first_setup, ctx
        )
    )
    
@state_handlers.register(ProfileStates.Delivery.Editables.Service)
async def delivery_edit_service_handler(ctx: Context, is_foreign_services: bool, **_):
    first_setup: bool = ctx.customer.privacy_data.delivery_info.service is None
    
    services = await ctx.services.db.delivery_services.get_all(is_foreign_services)
    
    await ctx.message.answer(
        ctx.t.ProfileTranslates.Delivery.service_text,
        reply_markup=ProfileKBs.Delivery.Editables.services(
            first_setup, services, ctx
        )
    )
    
@state_handlers.register(ProfileStates.Delivery.Editables.RequirementsLists)
async def delivery_edit_requirements_lists_handler(ctx: Context, service: DeliveryService, **_):
    first_setup: bool = ctx.customer.privacy_data.delivery_info.service is None
    lists = service.requirements_options
    
    await ctx.message.answer(
        ctx.t.ProfileTranslates.Delivery.requirements_list_text,
        reply_markup=ProfileKBs.Delivery.Editables.requirements_lists(
            first_setup, lists, ctx
        )
    )

@state_handlers.register(ProfileStates.Delivery.Editables.Requirement)
async def delivery_edit_requirement_handler(ctx: Context, service: DeliveryService, requirement_index: int = 0, **_):
    first_setup: bool = ctx.customer.privacy_data.delivery_info.service is None
    requirement = service.selected_option.requirements[requirement_index]
    
    await ctx.message.answer(
        ctx.t.ProfileTranslates.Delivery.requirement_value_text.format(name=requirement.name.get(ctx), description=requirement.description.get(ctx)),
        reply_markup=ProfileKBs.Delivery.Editables.requirement(
            first_setup, ctx
        )
    )

@state_handlers.register(ProfileStates.Delivery.Editables.SendToManualConfirmation)
async def delivery_edit_send_to_manual_confirmation_handler(ctx: Context, **_):
    await ctx.message.answer(ctx.t.ProfileTranslates.Delivery.send_to_manual_confirmation_text,
                             reply_markup=UncategorizedKBs.yes_no(ctx))

@state_handlers.register(ProfileStates.Delivery.DeleteConfimation)
async def delivery_delete_confirmation_handler(ctx: Context, **_):
    await ctx.message.answer(
        ctx.t.ProfileTranslates.Delivery.delete_confimation,
        reply_markup=UncategorizedKBs.yes_no(ctx)
    )
    
__all__ = [
    "call_state_handler",
    "AdminStates",
    "NewUserStates",
    "CommonStates",
    "AssortmentStates",
    "CartStates",
    "OrderStates",
    "ProfileStates"
]