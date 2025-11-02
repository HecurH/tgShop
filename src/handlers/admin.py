import datetime
import json

from aiogram import Bot, Router
from aiogram.filters import CommandObject, Command
from aiogram.types import BufferedInputFile
from pydantic import ValidationError
from pydantic_mongo import PydanticObjectId

from configs.supported import SUPPORTED_LANGUAGES_TEXT
from core.services.db import *

from core.helper_classes import Context
from core.middlewares import RoleCheckMiddleware
from core.states import AdminStates, CommonStates, call_state_handler
from schemas.enums import OrderStateKey, MediaType
from schemas.types import LocalizedMoney, LocalizedString, LocalizedSavedMedia, LocalizedEntry
from ui.message_tools import list_commands

router = Router(name="admin")
middleware = RoleCheckMiddleware("admin")

router.message.middleware.register(middleware)
router.callback_query.middleware.register(middleware)


@router.message(Command("help"))
async def help_handler(_, ctx: Context):
    txt = "\n".join(doc for _, doc in list_commands(router))
    
    await ctx.message.answer(txt, parse_mode=None)

@router.message(Command("update_media"))
async def help_handler(_, ctx: Context):
    """/update_media - Обновить кэш медиа"""
    
    await ctx.services.media_saver.update_cache()
    
    await ctx.message.answer("Обновлено!")



@router.message(Command("msg_to"))
async def msg_to_handler(_, ctx: Context, command: CommandObject):
    """/msg_to <user_id> - Отправить сообщение пользователю"""
    user_id = int(command.args) if command.args.isdigit() else None
    if not user_id:
        await ctx.message.answer("Неправильный формат команды")
        return
    
    customer = await ctx.services.db.customers.find_by_user_id(user_id)
    if not customer:
        await ctx.message.answer("Пользователь не найден")
        return

    await customer.save_in_fsm(ctx, "customer")
    await call_state_handler(AdminStates.Customers.AdminMessageSending, ctx, customer=customer)

@router.message(AdminStates.Customers.AdminMessageSending)
async def admin_message_sending_handler(_, ctx: Context):
    customer: Customer = await Customer.from_fsm_context(ctx, "customer")
    if ctx.message.text == ctx.t.UncategorizedTranslates.cancel:
        await call_state_handler(CommonStates.MainMenu, ctx, send_before=("Отменено", 1))
        return
    
    
    await ctx.services.notificators.UserTelegramNotificator.forward_admin_message(customer, ctx.message)
    await call_state_handler(CommonStates.MainMenu, ctx, send_before=("Сообщение отправлено.", 1))
    
@router.message(Command("confirm_manual_payment"))
async def confirm_manual_payment_handler(_, ctx: Context, command: CommandObject):
    """/confirm_manual_payment <order_id>|<datetime> - Подтвердить ручную оплату заказа"""
    args = command.args.split("|")
    if len(args) < 2:
        await ctx.message.answer(f"Недостаточно аргументов.")
        return
    
    order_id: str = args[0]
    try:
        parsed_datetime = datetime.datetime.fromisoformat(args[1])
    except ValueError as e:
        await ctx.message.answer(f"Неправильный формат времени: {e}")
        return
    
    order = await ctx.services.db.orders.find_one_by_id(PydanticObjectId(order_id)) if order_id else None
    customer = await ctx.services.db.customers.find_one_by_id(order.customer_id) if order else None
    if not order:
        await ctx.message.answer("Заказ не найден")
        return
    if not customer:
        await ctx.message.answer("Пользователь не найден")
        return
    
    if order.state != OrderStateKey.waiting_for_manual_payment_confirm:
        await ctx.message.answer("Заказ не в ожидании подтверждения оплаты")
        return
    
    order.price_details.customer_paid = True
    order.price_details.payment_time = parsed_datetime
    order.state.set_state(OrderStateKey.accepted)
    
    if not order.payment_method.can_register_receipts:
        
        
        await ctx.services.notificators.UserTelegramNotificator.send_order_payment_accepted(customer, order)
        await ctx.services.db.orders.save(order)
        if await ctx.services.db.orders.count_customer_orders(customer) == 1 and customer.invited_by:
            if inviter := await ctx.services.db.inviters.find_one_by_id(customer.invited_by):
                if reward := await ctx.services.db.inviters.count_new_first_order(inviter, order, ctx):
                    inviter_customer = await ctx.services.db.customers.find_one_by_id(inviter.customer_id)
                    await ctx.services.notificators.UserTelegramNotificator.send_inviter_reward(inviter_customer, reward)
                    
                await ctx.services.db.inviters.save(inviter)
        
        await ctx.message.answer("Заказ подтвержден")
        return
    
    await order.save_in_fsm(ctx, "order")
    await call_state_handler(AdminStates.Order.AskGenerateReceipt, ctx)
    
@router.message(AdminStates.Order.AskGenerateReceipt)
async def ask_generate_receipt_handler(_, ctx: Context):
    text = ctx.message.text
    if not text: return
    if text not in [ctx.t.UncategorizedTranslates.yes, ctx.t.UncategorizedTranslates.no]:
        await call_state_handler(CommonStates.MainMenu, ctx, send_before=("Отменено.", 1))
        return

    order = await Order.from_fsm_context(ctx, "order")
    customer = await ctx.services.db.customers.find_one_by_id(order.customer_id)
    cart_entries = await ctx.services.db.cart_entries.find_entries_by_order(order)
    
    if text == ctx.t.UncategorizedTranslates.yes:
        try:
            receipts = await ctx.services.tax.invoice_by_order(cart_entries, order, order.price_details.payment_time)
        except Exception as e:
            await call_state_handler(CommonStates.MainMenu, ctx, send_before=(f"Ошибка при генерации чеков: {str(e)}", 1))
            return

        await ctx.services.notificators.UserTelegramNotificator.send_order_payment_accepted(customer, order, receipts)
    elif text == ctx.t.UncategorizedTranslates.no:
        await ctx.services.notificators.UserTelegramNotificator.send_order_payment_accepted(customer, order)
    
    
    await ctx.services.db.orders.save(order)
    if await ctx.services.db.orders.count_customer_orders(customer) == 1 and customer.invited_by:
        if inviter := await ctx.services.db.inviters.find_one_by_id(customer.invited_by):
            if reward := await ctx.services.db.inviters.count_new_first_order(inviter, order, ctx):
                inviter_customer = await ctx.services.db.customers.find_one_by_id(inviter.customer_id)
                await ctx.services.notificators.UserTelegramNotificator.send_inviter_reward(inviter_customer, reward)
                
            await ctx.services.db.inviters.save(inviter)
    
    await call_state_handler(CommonStates.MainMenu, ctx, send_before=("Заказ подтвержден", 1))
    
@router.message(Command("unform_order"))
async def unform_order_handler(_, ctx: Context, command: CommandObject):
    """/unform_order <order_id> - Расформировать заказ"""
    order_id: str = command.args
    order = await ctx.services.db.orders.find_one_by_id(PydanticObjectId(order_id)) if order_id else None
    customer = await ctx.services.db.customers.find_one_by_id(order.customer_id) if order else None
    if not order:
        await ctx.message.answer("Заказ не найден")
        return
    if not customer:
        await ctx.message.answer("Пользователь не найден")
        return
    
    if order.state != OrderStateKey.waiting_for_manual_payment_confirm:
        await ctx.message.answer("Заказ не в ожидании подтверждения оплаты")
        return
    
    
    await order.save_in_fsm(ctx, "order")
    await customer.save_in_fsm(ctx, "customer")
    await call_state_handler(AdminStates.Order.UnformAskForComment, ctx, customer=customer)

@router.message(AdminStates.Order.UnformAskForComment)
async def unform_ask_for_comment_handler(_, ctx: Context):
    text = ctx.message.text
    if not text: return
    if text == ctx.t.UncategorizedTranslates.cancel:
        await call_state_handler(CommonStates.MainMenu, ctx, send_before=("Отменено.", 1))
        return

    order: Order = await Order.from_fsm_context(ctx, "order")
    customer = await Customer.from_fsm_context(ctx, "customer")
    
    if text == "0":
        await ctx.services.notificators.UserTelegramNotificator.send_order_unformed(customer, order)
    else:
        await ctx.services.notificators.UserTelegramNotificator.send_order_unformed_with_reason(customer, order, text)
    cart_entries = await ctx.services.db.cart_entries.find_entries_by_order(order)
    await ctx.services.db.orders.delete(order)
    for entry in cart_entries:
        entry.order_id = None
        entry.frozen_product = None
    
    await ctx.services.db.cart_entries.save_many(cart_entries)
    
    await ctx.services.db.customers.add_bonus_money(customer, order.price_details.bonuses_applied, ctx)
    if order.promocode_id:
        await ctx.services.db.promocodes.update_usage(order.promocode_id, -1)
        
    await call_state_handler(CommonStates.MainMenu, ctx, send_before=("Успешно.", 1))

@router.message(Command("confirm_order_price"))
async def admin_confirm_price_handler(_, ctx: Context, command: CommandObject):
    """/confirm_order_price <order_id> - Подтвердить цену заказа"""
    order_id: str = command.args
    order = await ctx.services.db.orders.find_one_by_id(PydanticObjectId(order_id)) if order_id else None
    if not order:
        await ctx.message.answer("Заказ не найден")
        return
    
    entries = list(await ctx.services.db.cart_entries.find_price_confirmation_entries(order))
    if order.state != OrderStateKey.waiting_for_price_confirmation or not entries:
        await ctx.message.answer("Заказ не в ожидании подтверждения цены")
        return
    
    await order.save_in_fsm(ctx, "order")
    await call_state_handler(AdminStates.Order.PriceConfirmationWaiting, ctx, entries=entries)
    
@router.message(AdminStates.Order.PriceConfirmationWaiting)
async def price_confirmation_waiting_handler(_, ctx: Context):
    text = ctx.message.text
    if not text: return
    if text == ctx.t.UncategorizedTranslates.cancel:
        await call_state_handler(CommonStates.MainMenu, ctx, send_before=("Отменено.", 1))
        return
    
    #формат данных = 0: [{"color": {"data": {"RUB": {"currency": "RUB", "amount": 0.0}, "USD": {"currency": "USD", "amount": 0.0}}}}]\n1: [{"color": {"data": {"RUB": {"currency": "RUB", "amount": 0.0}, "USD": {"currency": "USD", "amount": 0.0}}}}]
    try:
        entries = []
        for line in text.strip().split('\n'):
            if not line.strip() or ': ' not in line:
                continue
            _, json_part = line.split(': ', 1)
            entry_data = json.loads(json_part)
            entries.extend({
                k: LocalizedMoney.model_validate(v)
                for item in entry_data
                for k, v in item.items()
            } for item in entry_data)
            
        if not entries:
            await ctx.message.answer("Неверный формат данных")
            return
            
    except (ValueError, json.JSONDecodeError, ValidationError):
        await ctx.message.answer("Ошибка при обработке данных")
        return
    
    order: Order = await Order.from_fsm_context(ctx, "order")
    customer = await ctx.services.db.customers.find_one_by_id(order.customer_id)
    if not customer:
        await ctx.message.answer("Пользователь не найден")
        return
    
    cart_entries = list(await ctx.services.db.cart_entries.find_price_confirmation_entries(order))
    
    for idx, cart_entry in enumerate(cart_entries):
        updater_entry = entries[idx]
        for key, price in updater_entry.items():
            chosen = cart_entry.configuration.options[key].get_chosen()
            chosen.price = price
        
        cart_entry.configuration.price_confirmed_override = True
        cart_entry.configuration.update_price()
    await ctx.services.db.cart_entries.save_many(cart_entries)
        
    order.state.set_state(OrderStateKey.waiting_for_forming)
    
    products_price = await ctx.services.db.cart_entries.calculate_cart_entries_price_by_order(order)
    order.price_details = OrderPriceDetails.new(customer, products_price)
    
    
    await ctx.services.db.orders.save(order)
    
    await ctx.services.notificators.UserTelegramNotificator.send_order_price_confirmed(customer)
    await call_state_handler(CommonStates.MainMenu, ctx, send_before=("Цена подтверждена.", 1))
    
#command like /manual_delivery_price <user_id> <delivery_service_id> <req_options_list_idx> <json dumped list of securs> <serialized LocalizedMoney>
@router.message(Command("manual_delivery_price"))
async def manual_delivery_price_handler(_, ctx: Context, command: CommandObject):
    """/manual_delivery_price <user_id> <delivery_service_id> <req_options_list_idx> <json dumped list of securs> <serialized LocalizedMoney> - Установить цену доставки"""
    if not command.args:
        await ctx.message.answer("Неверный формат команды")
        return
        
    args = command.args.split(maxsplit=4)  # разделяем только первые 4 аргумента
    
    if len(args) < 5:
        await ctx.message.answer("Неверный формат команды")
        return
        
    user_id = int(args[0]) if args[0].isdigit() else None
    delivery_service_id = args[1]
    req_options_list_idx = int(args[2])
    
    # начало и конец JSON
    json_start = command.args.find('[')
    json_end = command.args.find(']')
    
    if json_start == -1 or json_end == -1:
        await ctx.message.answer("Неверный формат JSON")
        return
        
    securs: str = command.args[json_start:json_end+1]
        
    # все что после JSON и до конца строки - это price
    price_str = command.args[json_end+1:].strip()
    try:
        price = LocalizedMoney.model_validate_json(price_str)
    except:
        await ctx.message.answer("Неверный формат цены")
        return
    
    customer = await ctx.services.db.customers.find_one_by({"user_id": user_id})
    delivery_service = await ctx.services.db.delivery_services.find_one_by_id(PydanticObjectId(delivery_service_id)) if delivery_service_id else None
    
    if not customer or not delivery_service:
        await ctx.message.answer("Пользователь или сервис доставки не найдены")
        return
    
    if customer.delivery_info and customer.delivery_info.service:
        await ctx.message.answer("У пользователя уже выбран другой сервис доставки")
        return
    if not customer.waiting_for_manual_delivery_info_confirmation:
        await ctx.message.answer("Пользователь уже не ждет подтверждения цены")
        return
    
    delivery_service.selected_option = delivery_service.requirements_options[req_options_list_idx]
    delivery_service.restore_securs_from_str(securs)
    delivery_service.price = price
    customer.delivery_info = DeliveryInfo()
    customer.delivery_info.service = delivery_service
    customer.waiting_for_manual_delivery_info_confirmation = False
    await ctx.services.db.customers.save(customer)
    
    await ctx.services.notificators.UserTelegramNotificator.send_delivery_price_confirmed(customer)
    
    await ctx.message.answer("Цена установлена!")

@router.message(Command("cancel_manual_delivery_price_confirm"))
async def cancel_manual_delivery_price_confirm_handler(_, ctx: Context, command: CommandObject):
    """/cancel_manual_delivery_price_confirm <user_id> - Отклонить подтверждение цены доставки"""
    args = command.args
    user_id = int(args) if args and args.isdigit() else None
    customer = await ctx.services.db.customers.find_one_by({"user_id": user_id}) if user_id else None

    if not customer:
        await ctx.message.answer("Пользователь не найден")
        return
    
    if not customer.waiting_for_manual_delivery_info_confirmation:
        await ctx.message.answer("Пользователь не не ожидает подтверждения")
        return
    
    await customer.save_in_fsm(ctx, "customer")
    await call_state_handler(AdminStates.Delivery.PriceConfirmationCancel, ctx, customer=customer)
    
@router.message(AdminStates.Delivery.PriceConfirmationCancel)
async def price_confirmation_cancel_handler(_, ctx: Context):
    text = ctx.message.text
    if not text: return
    if text == ctx.t.UncategorizedTranslates.cancel:
        await call_state_handler(CommonStates.MainMenu, ctx, send_before=("Отменено.", 1))
        return
    customer: Customer = await Customer.from_fsm_context(ctx, "customer")
    
    customer.waiting_for_manual_delivery_info_confirmation = False
    await ctx.services.db.customers.save(customer)
    await ctx.fsm.update_data(customer=None)
    
    if text == "0":
        await ctx.services.notificators.UserTelegramNotificator.send_delivery_price_rejected(customer)
    else:
        await ctx.services.notificators.UserTelegramNotificator.send_delivery_price_rejected_with_reason(customer, text)
    await call_state_handler(CommonStates.MainMenu, ctx, send_before=("Успешно.", 1))
        

@router.message(Command("save_photo"))
async def photo_saving_handler(_, ctx: Context):
    raw = await ctx.message.bot.download(ctx.message.document)

    msg_id = await ctx.message.answer_photo(photo=BufferedInputFile(
        raw.read(),
        filename=ctx.message.document.file_name
    )
    )
    await ctx.message.answer(msg_id.photo[-1].file_id)

@router.message(Command("save_video"))
async def video_saving_handler(_, ctx: Context):
    raw = await ctx.message.bot.download(ctx.message.document)

    msg_id = await ctx.message.answer_video(video=BufferedInputFile(
        raw.read(),
        filename=ctx.message.document.file_name
    )
    )
    await ctx.message.answer(msg_id.video.file_id)
    
@router.message(Command("save_file"))
async def file_saving_handler(_, ctx: Context):
    bot: Bot = ctx.message.bot
    
    raw = await bot.download(ctx.message.document)

    msg_id = await ctx.message.answer_document(document=BufferedInputFile(
        raw.read(),
        filename=ctx.message.document.file_name
    )
    )
    await ctx.message.answer(msg_id.document.file_id)

@router.message(Command("add_cats"))
async def cats_handler(_, ctx: Context) -> None:
    cat = Category(
        name="dildos",
        localized_name=LocalizedString(data={
                "ru": "Дилдо",
                "en": "Dildos"
            }))
    await ctx.services.db.categories.save(cat)
    cat = Category(
        name="masturbators",
        localized_name=LocalizedString(data={
                "ru": "Мастурбаторы",
                "en": "Masturbators"
            }))
    await ctx.services.db.categories.save(cat)
    # cat = Category(
    #     name="anal_plugs",
    #     localized_name=LocalizedString(data={
    #             "ru": "Анальные пробки",
    #             "en": "Anal plugs"
    #         }))
    # await ctx.services.db.categories.save(cat)

    cat = Category(
        name="other",
        localized_name=LocalizedString(data={
                "ru": "Другое",
                "en": "Other"
            }))
    await ctx.services.db.categories.save(cat)


@router.message(Command("add_products"))
async def image_saving_handler(_, ctx: Context) -> None:
    haiden_configuration = ProductConfiguration(options={
        "size": ConfigurationOption(
            name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Size.name"),
            text=LocalizedEntry(path="ProductConfigurationTranslates.Options.Size.text"),
            chosen_key="medium",
            choices={
                "small": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Size.Choices.Small.name"),
                    media=LocalizedSavedMedia(media_key="photo_haiden_configuration_size_small"),
                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Size.Choices.Small.description"),

                    price=LocalizedMoney.from_keys(RUB=-1500.00, USD=-30.00)
                ),
                "medium": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Size.Choices.Medium.name"),
                    media=LocalizedSavedMedia(media_key="photo_haiden_configuration_size_medium"),
                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Size.Choices.Medium.description")
                ),
                "large": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Size.Choices.Large.name"),
                    media=LocalizedSavedMedia(media_key="photo_haiden_configuration_size_large"),
                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Size.Choices.Large.description"),

                    price=LocalizedMoney.from_keys(RUB=1500.00, USD=30.00)
                )
            }
        ),
        "firmness": ConfigurationOption(
            name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Firmness.name"),
            text=LocalizedEntry(path="ProductConfigurationTranslates.Options.Firmness.text"),
            chosen_key="medium",
            choices={
                "soft": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Firmness.Choices.Soft.name"),
                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Firmness.Choices.Soft.description"),
                ),
                "medium": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Firmness.Choices.Medium.name"),
                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Firmness.Choices.Medium.description"),
                ),
                "firm": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Firmness.Choices.Firm.name"),
                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Firmness.Choices.Firm.description"),
                ),
                "firmness_gradation": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Firmness.Choices.FirmnessGradation.name"),
                    media=LocalizedSavedMedia(media_key="photo_dildos_configuration_firmness_gradation"),
                    is_custom_input=True,
                    can_be_blocked_by=["color/swirl"],

                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Firmness.Choices.FirmnessGradation.description"),
                    price=LocalizedMoney.from_keys(RUB=400.00, USD=6.00)
                )
            }
        ),
        "color": ConfigurationOption(
            name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.name"),
            text=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.text"),
            chosen_key="canonical",
            choices={
                "canonical": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Canonical.name"),
                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Canonical.description"),
                    media=LocalizedSavedMedia(media_key="photo_haiden_configuration_color_canonical"),
                    price=LocalizedMoney.from_keys(RUB=800.00, USD=12.00),
                    can_be_blocked_by=["color/additionals/gradient",
                                       "color/additionals/glitter",
                                       "color/additionals/shimmer",
                                       "color/additionals/neon_colors",
                                       "color/additionals/phosphors/blue",
                                       "color/additionals/phosphors/cyan",
                                       "color/additionals/phosphors/green",
                                       "color/additionals/phosphors/red",
                                       "color/additionals/phosphors/purple",
                                       "color/additionals/phosphors/white",
                                       ],
                ),
                "existing_set": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.ExistingSet.name"),
                    media=LocalizedSavedMedia(media_key="photo_configuration_color_existing_set"),
                    existing_presets=True,
                    existing_presets_pattern="K|D,T|P,M,N|int",
                    price_by_preset={
                        "T": LocalizedMoney.from_keys(RUB=300.00, USD=6.00),
                        "P": LocalizedMoney.from_keys(RUB=300.00, USD=6.00),
                        "N": LocalizedMoney.from_keys(RUB=300.00, USD=6.00)
                        },
                    can_be_blocked_by=["color/additionals/glitter",
                                       "color/additionals/shimmer",
                                       "color/additionals/neon_colors",
                                       "color/additionals/phosphors/blue",
                                       "color/additionals/phosphors/cyan",
                                       "color/additionals/phosphors/green",
                                       "color/additionals/phosphors/red",
                                       "color/additionals/phosphors/purple",
                                       "color/additionals/phosphors/white",
                                       ],

                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.ExistingSet.description")
                ),
                "two-zone": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.TwoZone.name"),
                    media=LocalizedSavedMedia(media_key="photo_configuration_color_two-zone"),
                    is_custom_input=True,

                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.TwoZone.description"),
                ),
                "three-zone": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.ThreeZone.name"),
                    media=LocalizedSavedMedia(media_key="photo_configuration_color_three-zone"),
                    is_custom_input=True,
                    price=LocalizedMoney.from_keys(RUB=500.00, USD=10.00),

                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.ThreeZone.description")
                ),
                "swirl": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Swirl.name"),
                    media=LocalizedSavedMedia(media_key="photo_configuration_color_swirl"),
                    is_custom_input=True,
                    can_be_blocked_by=["firmness/firmness_gradation"],
                    price=LocalizedMoney.from_keys(RUB=600.00, USD=10.00),

                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Swirl.description"),
                ),
                "custom": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Custom.name"),
                    is_custom_input=True,
                    blocks_price_determination=True,
                    price=LocalizedMoney.from_keys(RUB=2000.00, USD=30.00),

                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Custom.description"),
                ),
                "additionals": ConfigurationSwitches(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.name"),
                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.description"),
                    switches={
                        "gradient": ConfigurationSwitch(
                            name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.Gradient.name"),
                            description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.Gradient.description"),
                            price=LocalizedMoney.from_keys(RUB=600.00, USD=10.00),
                            can_be_blocked_by=["color/canonical"]
                        ),
                        "glitter": ConfigurationSwitch(
                            name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.Glitter.name"),
                            description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.Glitter.description"),
                            price=LocalizedMoney.from_keys(RUB=400.00, USD=8.00),
                            can_be_blocked_by=["color/existing_set",
                                               "color/canonical"]
                        ),
                        "shimmer": ConfigurationSwitch(
                            name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.Shimmer.name"),
                            description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.Shimmer.description"),
                            price=LocalizedMoney.from_keys(RUB=300.00, USD=6.00),
                            can_be_blocked_by=["color/existing_set",
                                               "color/canonical"]
                        ),
                        "neon_colors": ConfigurationSwitch(
                            name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.NeonColors.name"),
                            description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.NeonColors.description"),
                            price=LocalizedMoney.from_keys(RUB=300.00, USD=6.00),
                            can_be_blocked_by=["color/existing_set",
                                               "color/canonical"]
                        ),
                        "phosphors": ConfigurationSwitchesGroup(
                            name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.PhosphorsGroup.name"),
                            description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.PhosphorsGroup.description"),
                            switches={
                                "blue": ConfigurationSwitch(
                                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.PhosphorsGroup.Switches.Blue.name"),
                                    price=LocalizedMoney.from_keys(RUB=600.00, USD=10.00),
                                    can_be_blocked_by=["color/existing_set",
                                                       "color/canonical"]
                                ),
                                "cyan": ConfigurationSwitch(
                                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.PhosphorsGroup.Switches.Cyan.name"),
                                    price=LocalizedMoney.from_keys(RUB=400.00, USD=8.00),
                                    can_be_blocked_by=["color/existing_set",
                                                       "color/canonical"]
                                ),
                                "green": ConfigurationSwitch(
                                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.PhosphorsGroup.Switches.Green.name"),
                                    price=LocalizedMoney.from_keys(RUB=400.00, USD=8.00),
                                    can_be_blocked_by=["color/existing_set",
                                                       "color/canonical"]
                                ),
                                "red": ConfigurationSwitch(
                                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.PhosphorsGroup.Switches.Red.name"),
                                    price=LocalizedMoney.from_keys(RUB=800.00, USD=12.00),
                                    can_be_blocked_by=["color/existing_set",
                                                       "color/canonical"]
                                ),
                                "purple": ConfigurationSwitch(
                                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.PhosphorsGroup.Switches.Purple.name"),
                                    price=LocalizedMoney.from_keys(RUB=800.00, USD=12.00),
                                    can_be_blocked_by=["color/existing_set",
                                                       "color/canonical"]
                                ),
                                "white": ConfigurationSwitch(
                                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.PhosphorsGroup.Switches.White.name"),
                                    price=LocalizedMoney.from_keys(RUB=800.00, USD=12.00),
                                    can_be_blocked_by=["color/existing_set",
                                                       "color/canonical"]
                                )
                                
                                    
                            }
                        )
                    }
                ),
                "available_colors": ConfigurationAnnotation(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.AvailableColors.name"),
                    text=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.AvailableColors.text"),
                    media=LocalizedSavedMedia(media_key="photo_configuration_color_available_colors"),
                )
            }
        )
    })

    haiden_product = Product(
        name=LocalizedString(data={
            "ru":"Дракон Хайден",
            "en":"Haiden Dragon"}
        ),
        name_for_tax="Индивидуальная отливка силиконового изделия \"Дракон Хайден\"",
        category="dildos",
        short_description_media=LocalizedSavedMedia(media_key="photo_haiden_full_photo"),
        long_description=LocalizedString(data={
            "ru":"""<blockquote expandable>Нежное сияние пурпурной драконьей чешуи под лучами алого заката. Хайден всегда знает, как позаботиться о своём любимом партнёре. Мягко обхватывая тебя своими опытными лапками, чутко лаская чувствительные зоны, он приближается всё ближе и ближе, заставляя твоё тело легко подрагивать от возбуждения. Он улавливает твоё сбитое дыхание, чуть улыбаясь от удовольствия... 

Его кончик нежно входит в тебя, заставляя постанывать и дрожать еще сильнее. Постепенно расширяясь, мягко входят сплетения, доходя до окончательно добивающего узла... 
Сильный и нежный, дракон Хайден будет идеальным партнёром, дарящим мягкие ласки и доминирущее превосходство, ведь все бурные фантазии, воплощаемые в жизнь, зависят только от твоего желания~</blockquote>

<b>К заказу будет приложен ламинированный плакат А5!</b>""",
            "en":"""<blockquote expandable>The tender gleam of purple dragon scales under the rays of the scarlet sunset. Hayden always knows how to take care of his beloved partner. Gently holding you with his experienced paws, sensitively caressing your sensitive zones, he draws closer and closer, making your body tremble lightly with excitement. He catches your ragged breath, smiling slightly with pleasure...

His tip gently enters you, making you moan and tremble even more. Gradually expanding, the soft knots slip in, reaching the final, overwhelming knot...
Strong and tender, the dragon Hayden will be the perfect partner, bestowing soft caresses and dominant superiority, for all the wild fantasies brought to life depend only on your desire~</blockquote>

<b>An A5 laminated poster will be included with the order!</b>"""}
        ),
        long_description_media=LocalizedSavedMedia(media_key="photo_haiden_full_photo"),
        base_price=LocalizedMoney.from_keys(RUB=6000.00, USD=100.00),
        configuration=haiden_configuration,
        configuration_media=LocalizedSavedMedia(media_key="photo_haiden_full_photo"),
    )

    morion_configuration = haiden_configuration.model_copy(deep=True)
    morion_configuration.options["size"].choices["small"].media = LocalizedSavedMedia(media_key="photo_morion_configuration_size_small")
    morion_configuration.options["size"].choices["medium"].media = LocalizedSavedMedia(media_key="photo_morion_configuration_size_medium")
    morion_configuration.options["size"].choices["large"].media = LocalizedSavedMedia(media_key="photo_morion_configuration_size_large")
    
    
    morion_configuration.options["color"].choices["canonical"].media = LocalizedSavedMedia(media_key="photo_morion_configuration_color_canonical")
    
    morion_product = Product(
        name=LocalizedString(data={
            "ru":"Конь Морион",
            "en":"Colt Morion"}
        ),
        name_for_tax="Индивидуальная отливка силиконового изделия \"Конь Морион\"",
        category="dildos",
        short_description_media=LocalizedSavedMedia(media_key="photo_morion_full_photo"),
        long_description=LocalizedString(data={
            "ru":"""Питончик ещё не притащил описание... подождём, пока он распутает свой хвост 🐍""",
            "en":"""Питончик ещё не притащил описание... подождём, пока он распутает свой хвост 🐍"""}
        ),
        long_description_media=LocalizedSavedMedia(media_key="photo_morion_full_photo"),
        base_price=LocalizedMoney.from_keys(RUB=6000.00, USD=100.00),
        configuration=morion_configuration,
        configuration_media=LocalizedSavedMedia(media_key="photo_morion_full_photo"),
    )
    
    avily_configuration = haiden_configuration.model_copy(deep=True)
    avily_configuration.options["size"].choices["small"].media = LocalizedSavedMedia(media_key="photo_avily_configuration_size_small")
    avily_configuration.options["size"].choices["medium"].media = LocalizedSavedMedia(media_key="photo_avily_configuration_size_medium")
    avily_configuration.options["size"].choices["large"].media = LocalizedSavedMedia(media_key="photo_avily_configuration_size_large")
    
    
    avily_configuration.options["color"].choices["canonical"].media = LocalizedSavedMedia(media_key="photo_avily_configuration_color_canonical")
    
    avily_product = Product(
        name=LocalizedString(data={
            "ru":"Авали Авили",
            "en":"Avali Avily"}
        ),
        name_for_tax="Индивидуальная отливка силиконового изделия \"Авали Авили\"",
        category="dildos",
        short_description_media=LocalizedSavedMedia(media_key="photo_avily_full_photo"),
        long_description=LocalizedString(data={
            "ru":"""<blockquote expandable>Беззвучное движение мягких перьев, едва заметное неловко брошенному взгляду... 
Пернатый проказник Авили, прославившийся своим умением незаметно подкрадываться со спины, утягивая свою жертву ловким движением лап, обладает очень интересной особенностью: вначале узкий, как течение маленького ручья, затем плавно расширяющийся в небольшую реку, а после превращающийся в мощный водный поток, достигая кульминации, впадающий в объёмное озеро, такое крупное и необъятное, но невероятно манящее...</blockquote>""",
            "en":"""<blockquote expandable>The soundless motion of soft feathers, barely noticeable to a clumsily cast glance...
The feathered mischief-maker Avili, famous for his ability to stealthily sneak up from behind and snatch his victim with a deft movement of his paws, possesses a very interesting feature: at first narrow, like the flow of a small stream, then smoothly widening into a small river, and then transforming into a powerful water stream, reaching its climax, it flows into a vast lake, so large and boundless, yet incredibly alluring...</blockquote>"""}
        ),
        long_description_media=LocalizedSavedMedia(media_key="photo_avily_full_photo"),
        base_price=LocalizedMoney.from_keys(RUB=6000.00, USD=100.00),
        configuration=avily_configuration,
        configuration_media=LocalizedSavedMedia(media_key="photo_avily_full_photo"),
    )
    
    ragnar_configuration = haiden_configuration.model_copy(deep=True)
    ragnar_options = {"poster": ConfigurationOption(
            name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Poster.name"),
            text=LocalizedEntry(path="ProductConfigurationTranslates.Options.Poster.text"),
            chosen_key="sfw",
            choices={
                "sfw": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Poster.Choices.SFW.name"),
                    media=LocalizedSavedMedia(media_key="photo_ragnar_configuration_poster_sfw"),
                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Poster.Choices.SFW.description")
                ),
                "nsfw": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Poster.Choices.NSFW.name"),
                    media=LocalizedSavedMedia(media_key="photo_ragnar_configuration_poster_nsfw"),
                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Poster.Choices.NSFW.description")
                )
            }
        )}
    ragnar_options.update(ragnar_configuration.options)
    ragnar_configuration.options = ragnar_options
    
    ragnar_configuration.options["size"].choices["small"].media = LocalizedSavedMedia(media_key="photo_ragnar_configuration_size_small")
    ragnar_configuration.options["size"].choices["medium"].media = LocalizedSavedMedia(media_key="photo_ragnar_configuration_size_medium")
    ragnar_configuration.options["size"].choices["large"].media = LocalizedSavedMedia(media_key="photo_ragnar_configuration_size_large")
    
    
    ragnar_configuration.options["color"].choices["canonical"].media = LocalizedSavedMedia(media_key="photo_ragnar_configuration_color_canonical")
    
    ragnar_product = Product(
        name=LocalizedString(data={
            "ru":"Волк Рагнар",
            "en":"Wolf Ragnar"}
        ),
        name_for_tax="Индивидуальная отливка силиконового изделия \"Волк Рагнар\"",
        category="dildos",
        short_description_media=LocalizedSavedMedia(media_key="photo_ragnar_full_photo"),
        long_description=LocalizedString(data={
            "ru":"""<blockquote expandable>Крупное, мощное тело, стальные мускулы, перекатывающиеся под толстой шкурой с густой серебристой шерстью... Огромный волк с тяжёлым рокотом дышит в твою спину, взгляд его ледяных жёлтых глаз пробивает твоё тело насквозь. Свирепо обнажая ряды блестящих зубов, своей мощной лапой он хватает тебя за талию, заставляя дрожать от лёгкого страха и предвкушения невероятного удовольствия...

Небольшой кончик входит внутрь, давая какое-то время для привычки к этому зверю, а затем ствол входит глубже, давая почувствовать свой плавный изгиб. Заставив подумать, что на этом всё заканчивается, он вводит внутрь мощный узел, добивая окончательно...

Первобытная машина грубой силы и неумолимых желаний, настоящий дикий зверь, сбежавший из северного леса, чтобы доставить вашему телу и разуму безудержное наслаждение. </blockquote>

<b>К заказу будет приложен ламинированный плакат А5 — SFW или NSFW версия на выбор.</b>""",
            "en":"""<blockquote expandable>A large, powerful body, steel-like muscles rippling beneath thick hide covered in dense, silvery fur... A massive wolf breathes with a low growl against your back, the gaze of its icy yellow eyes piercing right through you. Baring rows of gleaming teeth in a ferocious snarl, its powerful paw grabs you by the waist, making you tremble with a mix of slight fear and anticipation of incredible pleasure...

The small tip enters inside, giving you a moment to grow accustomed to the beast, before the shaft sinks deeper, letting you feel its smooth curve. Just as you think it's over, he pushes the thick knot inside, claiming you completely...

A primal engine of raw force and relentless desire, a true wild beast that escaped the northern forests to deliver untamed ecstasy to your body and mind.</blockquote>

<b>The order will be accompanied by an A5 — SFW laminated poster or an NSFW version to choose from.</b>"""}
        ),
        long_description_media=LocalizedSavedMedia(media_key="photo_ragnar_full_photo"),
        base_price=LocalizedMoney.from_keys(RUB=6000.00, USD=100.00),
        configuration=ragnar_configuration,
        configuration_media=LocalizedSavedMedia(media_key="photo_ragnar_full_photo"),
    )
    
    driana_configuration = haiden_configuration.model_copy(deep=True)
    
    driana_options = {"poster": ConfigurationOption(
            name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Poster.name"),
            text=LocalizedEntry(path="ProductConfigurationTranslates.Options.Poster.text"),
            chosen_key="sfw",
            choices={
                "sfw": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Poster.Choices.SFW.name"),
                    media=LocalizedSavedMedia(media_key="photo_driana_configuration_poster_sfw"),
                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Poster.Choices.SFW.description")
                ),
                "nsfw": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Poster.Choices.NSFW.name"),
                    media=LocalizedSavedMedia(media_key="photo_driana_configuration_poster_nsfw"),
                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Poster.Choices.NSFW.description")
                )
            }
        )}
    driana_options.update(driana_configuration.options)
    driana_configuration.options = driana_options
    
    driana_configuration.options["size"] = ConfigurationOption(
        name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Size.name"),
        text=LocalizedEntry(path="ProductConfigurationTranslates.Options.Size.text"),
        chosen_key="standart",
        choices={
            "standart": ConfigurationChoice(
                name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Size.Choices.Standart.name"),
                media=LocalizedSavedMedia(media_key="photo_driana_configuration_size_standart"),
                description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Size.Choices.Standart.description")
            )
        }
    )
 
    driana_configuration.options["firmness"] = ConfigurationOption(
        name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Firmness.name"),
        text=LocalizedEntry(path="ProductConfigurationTranslates.Options.Firmness.text"),
        chosen_key="ultra_soft",
        choices={
            "ultra_soft": ConfigurationChoice(
                name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Firmness.Choices.UltraSoft.name"),
                description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Firmness.Choices.UltraSoft.description"),
            ),
            "very_soft": ConfigurationChoice(
                name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Firmness.Choices.VerySoft.name"),
                description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Firmness.Choices.VerySoft.description"),
            ),
            "soft": ConfigurationChoice(
                name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Firmness.Choices.Soft.name"),
                description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Firmness.Choices.Soft.description"),
            ),
            "firmness_gradation": ConfigurationChoice(
                name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Firmness.Choices.DrianaFirmnessGradation.name"),
                media=LocalizedSavedMedia(media_key="photo_driana_configuration_firmness_gradation"),
                is_custom_input=True,
                can_be_blocked_by=["color/swirl"],

                description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Firmness.Choices.DrianaFirmnessGradation.description"),
                price=LocalizedMoney.from_keys(RUB=1000.00, USD=10.00)
            ),
            "extended_firmness_gradation": ConfigurationChoice(
                name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Firmness.Choices.DrianaExtendedFirmnessGradation.name"),
                media=LocalizedSavedMedia(media_key="photo_driana_configuration_extended_firmness_gradation"),
                is_custom_input=True,
                can_be_blocked_by=["color/swirl"],

                description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Firmness.Choices.DrianaExtendedFirmnessGradation.description"),
                price=LocalizedMoney.from_keys(RUB=1800.00, USD=19.00)
            )
        }
    )
 
    driana_configuration.options["color"] = ConfigurationOption(
        name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.name"),
        text=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.text"),
        chosen_key="canonical",
        choices={
            "canonical": ConfigurationChoice(
                name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Canonical.name"),
                description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Canonical.description"),
                media=LocalizedSavedMedia(media_key="photo_driana_configuration_color_canonical"),
                price=LocalizedMoney.from_keys(RUB=800.00, USD=12.00),
                can_be_blocked_by=["color/additionals/gradient",
                                    "color/additionals/glitter",
                                    "color/additionals/shimmer",
                                    "color/additionals/neon_colors",
                                    "color/additionals/phosphors/blue",
                                    "color/additionals/phosphors/cyan",
                                    "color/additionals/phosphors/green",
                                    "color/additionals/phosphors/red",
                                    "color/additionals/phosphors/purple",
                                    "color/additionals/phosphors/white",
                                    ],
            ),
            "existing_set": ConfigurationChoice(
                name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.ExistingSet.name"),
                media=LocalizedSavedMedia(media_key="photo_driana_configuration_color_existing_set"),
                existing_presets=True,
                existing_presets_pattern="K|D,T|P,M,N|int",
                price_by_preset={
                    "T": LocalizedMoney.from_keys(RUB=300.00, USD=6.00),
                    "P": LocalizedMoney.from_keys(RUB=300.00, USD=6.00),
                    "N": LocalizedMoney.from_keys(RUB=300.00, USD=6.00)
                    },
                can_be_blocked_by=["color/additionals/glitter",
                                    "color/additionals/shimmer",
                                    "color/additionals/neon_colors",
                                    "color/additionals/phosphors/blue",
                                    "color/additionals/phosphors/cyan",
                                    "color/additionals/phosphors/green",
                                    "color/additionals/phosphors/red",
                                    "color/additionals/phosphors/purple",
                                    "color/additionals/phosphors/white",
                                    ],

                description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.ExistingSet.description")
            ),
            "three-zone": ConfigurationChoice(
                name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.DrianaThreeZone.name"),
                media=LocalizedSavedMedia(media_key="photo_driana_configuration_color_four_zone"),
                is_custom_input=True,

                description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.DrianaThreeZone.description"),
            ),
            "swirl": ConfigurationChoice(
                name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Swirl.name"),
                media=LocalizedSavedMedia(media_key="photo_configuration_color_swirl"),
                is_custom_input=True,
                can_be_blocked_by=["firmness/firmness_gradation"],
                price=LocalizedMoney.from_keys(RUB=600.00, USD=10.00),

                description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Swirl.description"),
            ),
            "custom": ConfigurationChoice(
                name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Custom.name"),
                is_custom_input=True,
                blocks_price_determination=True,
                price=LocalizedMoney.from_keys(RUB=2000.00, USD=30.00),

                description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Custom.description"),
            ),
            "additionals": ConfigurationSwitches(
                name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.name"),
                description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.description"),
                switches={
                    "gradient": ConfigurationSwitch(
                        name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.Gradient.name"),
                        description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.Gradient.description"),
                        price=LocalizedMoney.from_keys(RUB=600.00, USD=10.00),
                        can_be_blocked_by=["color/canonical"]
                    ),
                    "glitter": ConfigurationSwitch(
                        name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.Glitter.name"),
                        description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.Glitter.description"),
                        price=LocalizedMoney.from_keys(RUB=400.00, USD=8.00),
                        can_be_blocked_by=["color/existing_set",
                                            "color/canonical"]
                    ),
                    "shimmer": ConfigurationSwitch(
                        name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.Shimmer.name"),
                        description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.Shimmer.description"),
                        price=LocalizedMoney.from_keys(RUB=300.00, USD=6.00),
                        can_be_blocked_by=["color/existing_set",
                                            "color/canonical"]
                    ),
                    "neon_colors": ConfigurationSwitch(
                        name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.NeonColors.name"),
                        description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.NeonColors.description"),
                        price=LocalizedMoney.from_keys(RUB=300.00, USD=6.00),
                        can_be_blocked_by=["color/existing_set",
                                            "color/canonical"]
                    ),
                    "phosphors": ConfigurationSwitchesGroup(
                        name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.PhosphorsGroup.name"),
                        description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.PhosphorsGroup.description"),
                        switches={
                            "blue": ConfigurationSwitch(
                                name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.PhosphorsGroup.Switches.Blue.name"),
                                price=LocalizedMoney.from_keys(RUB=600.00, USD=10.00),
                                can_be_blocked_by=["color/existing_set",
                                                    "color/canonical"]
                            ),
                            "cyan": ConfigurationSwitch(
                                name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.PhosphorsGroup.Switches.Cyan.name"),
                                price=LocalizedMoney.from_keys(RUB=400.00, USD=8.00),
                                can_be_blocked_by=["color/existing_set",
                                                    "color/canonical"]
                            ),
                            "green": ConfigurationSwitch(
                                name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.PhosphorsGroup.Switches.Green.name"),
                                price=LocalizedMoney.from_keys(RUB=400.00, USD=8.00),
                                can_be_blocked_by=["color/existing_set",
                                                    "color/canonical"]
                            ),
                            "red": ConfigurationSwitch(
                                name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.PhosphorsGroup.Switches.Red.name"),
                                price=LocalizedMoney.from_keys(RUB=800.00, USD=12.00),
                                can_be_blocked_by=["color/existing_set",
                                                    "color/canonical"]
                            ),
                            "purple": ConfigurationSwitch(
                                name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.PhosphorsGroup.Switches.Purple.name"),
                                price=LocalizedMoney.from_keys(RUB=800.00, USD=12.00),
                                can_be_blocked_by=["color/existing_set",
                                                    "color/canonical"]
                            ),
                            "white": ConfigurationSwitch(
                                name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Additionals.Switches.PhosphorsGroup.Switches.White.name"),
                                price=LocalizedMoney.from_keys(RUB=800.00, USD=12.00),
                                can_be_blocked_by=["color/existing_set",
                                                    "color/canonical"]
                            )
                            
                                
                        }
                    )
                }
            ),
            "available_colors": ConfigurationAnnotation(
                name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.AvailableColors.name"),
                text=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.AvailableColors.text"),
                media=LocalizedSavedMedia(media_key="photo_configuration_color_available_colors"),
            )
        }
    )
    
    
    driana_product = Product(
        name=LocalizedString(data={
            "ru":"Дракон Дриана",
            "en":"Dragon Driana"}
        ),
        name_for_tax="Индивидуальная отливка силиконового изделия \"Дракон Дриана\"",
        category="masturbators",
        short_description_media=LocalizedSavedMedia(media_key="photo_driana_full_photo"),
        long_description=LocalizedString(data={
            "ru":"""<blockquote expandable>Лунный свет струился по нежной чешуе, заставляя её сиять и переливаться. Тишина ночного озера, прерываемая лишь рокотом цикад. Плавные, мягкие движения Дрианы, осторожно спускающейся в воду... Она, рождённая от дракона и кобольда, соединила в себе их лучшие черты: изящное тело с тонкой талией, плавно переходящей в сочные и упругие широкие бёдра. 

Хрупкая, но такая привлекательная, она готова подарить вам невообразимые ласки и искреннюю нежность, доставить удовольствие, от которого закатят глаза даже самые искушённые!</blockquote>
Мастурбатор выполнен из самого мягкого силикона с невероятным внутренним рельефом. Игрушка идеально ложится в руку, что дарит дополнительное удобство использования — даже чешуйки на спине идеально прилегают к вашим пальцам.
Приобретая игрушку, вы приобретаете верную спутницу, готовую в любую минуту подарить вам наслаждение ~ 

<b>К заказу будет приложен ламинированный плакат А5 — SFW или NSFW версия на выбор.</b>""",
            "en":"""<blockquote expandable>Moonlight streamed over her delicate scales, making them shimmer and glisten. The silence of the night lake was broken only by the chirring of cicadas. The smooth, gentle movements of Dryana, carefully descending into the water... Born of a dragon and a kobold, she combined the best traits of both: an elegant body with a slender waist that gracefully curved into lush, firm, and wide hips.

Fragile yet so alluring, she is ready to grant you unimaginable caresses and sincere tenderness, to deliver a pleasure that will make even the most experienced roll their eyes!</blockquote>
The masturbator is made from the softest silicone with an incredible internal texture. The toy fits perfectly in your hand, providing additional comfort during use—even the scales on its back fit snugly against your fingers. When you purchase this toy, you acquire a faithful companion, ready at any moment to bestow upon you bliss ~

<b>The order will be accompanied by an A5 — SFW laminated poster or an NSFW version to choose from.</b>"""}
        ),
        long_description_media=LocalizedSavedMedia(media_key="photo_driana_full_photo"),
        base_price=LocalizedMoney.from_keys(RUB=6000.00, USD=100.00),
        configuration=driana_configuration,
        configuration_media=LocalizedSavedMedia(media_key="photo_driana_full_photo"),
    )
    
    lube_configuration = ProductConfiguration(options={
        "weight": ConfigurationOption(
            name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Weight.name"),
            text=LocalizedEntry(path="ProductConfigurationTranslates.Options.Weight.text"),
            chosen_key="10g",
            choices={
                "5g": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Weight.Choices.FiveGrams.name"),
                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Weight.Choices.FiveGrams.description"),
                    price=LocalizedMoney.from_keys(RUB=-150.00, USD=-1.50)
                ),
                "10g": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Weight.Choices.TenGrams.name"),
                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Weight.Choices.TenGrams.description")
                ),
                "50g": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Weight.Choices.FiftyGrams.name"),
                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Weight.Choices.FiftyGrams.description"),
                    price=LocalizedMoney.from_keys(RUB=1200.00, USD=12.00)
                ),
                "100g": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Weight.Choices.HundredGrams.name"),
                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Weight.Choices.HundredGrams.description"),
                    price=LocalizedMoney.from_keys(RUB=2700.00, USD=27.00)
                ),
                "200g": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Weight.Choices.TwoHundredGrams.name"),
                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Weight.Choices.TwoHundredGrams.description"),
                    price=LocalizedMoney.from_keys(RUB=5700.00, USD=57.00)
                )
            }
        )
    })
    
    lube_product = Product(
        name=LocalizedString(data={
            "ru":"Порошковая смазка",
            "en":"Powder lubricant"}
        ),
        name_for_tax="Модификация готовой порошковой смазки для улучшения характеристик хранения",
        category="other",
        short_description_media=LocalizedSavedMedia(media_key="photo_lube_full_photo"),
        long_description=LocalizedString(data={
            "ru":"""<b>Плюсы K-Lube:</b>
  - Инертная и безопасная к игрушкам
  - Долго высыхает 
  - Легко смывается водой с мылом

В отличие от J-Lube, который основан на кукурузном сиропе (то есть на органике), K-Lube сделан из неорганического материала. Следовательно, при соблюдении условий хранения готовая смазка может сохранять свои свойства минимум полгода (протестировано лично).
И чтобы Вы лично попробовали её и поняли, насколько она лучше готовых вариантов, к первому заказу от 5000 рублей будет вложен пробник на пять грамм!

Пяти грамм хватает на 200-400мл готовой смазки.

<b>Инструкция по применению: </b>
  1) В стерильную ёмкость влейте нужное количество <b>дистиллированной</b> воды.
  2) Высыпьте порошок в воду, <b>непрерывно помешивая</b> венчиком или вилкой до образования однородной массы.
  3) Залейте смазку в стерильную тару, дайте настояться несколько часов.
  4) Приятной игры!""",
            "en":"""<b>Advantages of K-Lube:</b>
  - Inert and safe for toys
  - Takes a long time to dry out
  - Easy to wash off with soap and water

Unlike J-Lube, which is based on corn syrup (i.e., an organic material), K-Lube is made from an inorganic material. Consequently, if stored properly, the prepared lubricant can retain its properties for at least six months (personally tested).
And so you can personally try it and see for yourself how much better it is than ready-made options, with your first order over 100 dollars, we will include a 5-gram sample!

Five grams is enough to make 200-400ml of prepared lubricant.

<b>Usage Instructions:</b>
  1) Pour the desired amount of <b>distilled</b> water into a sterile container.
  2) Pour the powder into the water, <b>stirring continuously</b> with a whisk or fork until a homogeneous mixture forms.
  3) Pour the lubricant into a sterile container and let it sit for a few hours.
  4) Enjoy!"""}
        ),
        long_description_media=LocalizedSavedMedia(media_key="photo_lube_full_photo"),
        base_price=LocalizedMoney.from_keys(RUB=300.00, USD=3.00),
        configuration=lube_configuration,
        configuration_media=LocalizedSavedMedia(media_key="photo_lube_full_photo"),
    )
    
    testers_configuration = ProductConfiguration(options={
        "firmness_kit": ConfigurationOption(
            name=LocalizedEntry(path="ProductConfigurationTranslates.Options.FirmnessKit.name"),
            text=LocalizedEntry(path="ProductConfigurationTranslates.Options.FirmnessKit.text"),
            chosen_key="N1",
            choices={
                "N1": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.FirmnessKit.Choices.N1.name"),
                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.FirmnessKit.Choices.N1.description")
                ),
                "N2": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.FirmnessKit.Choices.N2.name"),
                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.FirmnessKit.Choices.N2.description")
                ),
                "N3": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.FirmnessKit.Choices.N3.name"),
                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.FirmnessKit.Choices.N3.description")
                ),
            }
        )
    })
    
    testers_product = Product(
        name=LocalizedString(data={
            "ru":"Тестеры мягкости",
            "en":"Firmness testers"}
        ),
        name_for_tax="Индивидуальная отливка силиконовых тестеров",
        category="other",
        short_description_media=LocalizedSavedMedia(media_key="photo_testers_full_photo"),
        long_description=LocalizedString(data={
            "ru":"""Силиконовые тестеры мягкости, набор из трёх.
            
<b>Учтите, тестеры будут случайного цвета!</b>""",
            "en":"""Silicone softness testers, a set of three.
            
<b>Please note, the testers will be of random color!</b>"""}
        ),
        long_description_media=LocalizedSavedMedia(media_key="photo_testers_full_photo"),
        base_price=LocalizedMoney.from_keys(RUB=500.00, USD=10.00),
        configuration=testers_configuration,
        configuration_media=LocalizedSavedMedia(media_key="photo_testers_full_photo"),
    )
    
    # await ctx.services.db.products.save(haiden_product)
    # await ctx.services.db.products.save(morion_product)
    # await ctx.services.db.products.save(avily_product)
    # await ctx.services.db.products.save(ragnar_product)
    await ctx.services.db.products.save(driana_product)
    # await ctx.services.db.products.save(lube_product)
    # await ctx.services.db.products.save(testers_product)


@router.message(Command("add_additionals"))
async def addit(_, ctx: Context) -> None:
    additional = ProductAdditional(
        name=LocalizedString(data={
            "ru":"Присоска",
            "en":"Suction Cup"}
        ),
        category="dildos",
        price=LocalizedMoney.from_keys(RUB=600.00, USD=10.00)
    )

    await ctx.services.db.additionals.save(additional)
    
@router.message(Command("delete_acc"))
async def addit(_, ctx: Context) -> None:
    await ctx.services.db.customers.delete(ctx.customer)
    
@router.message(Command("add_delivery_services"))
async def addit(_, ctx: Context) -> None:
    service = DeliveryService(
        name=LocalizedString(data={
            "ru":"Почта России",
            "en":"Russian Post"
            }
        ),
        requirements_options=[
            DeliveryRequirementsList(
                name=LocalizedString(data={
                    "ru":"По номеру телефона",
                    "en":"By phone number"
                    }
                ),
                description=LocalizedString(data={
                    "ru":"описание того что почта россии может принимать отправления и по номеру телефона блахблах\nСервис доступен при условии разрешения получателем принимать посылки по номеру телефона.\nПодключить функцию можно в Личном кабинете или в мобильном приложении Почты России",
                    "en":"сначала на русском текст нормально надо написать про почту, а потом уже на английском емае"
                    }
                ),
                requirements=[
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"Номер телефона",
                            "en":"Phone number"
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"пишите номер в формате +7xxxxxxxxxx",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    )
                ]
            ),
            DeliveryRequirementsList(
                name=LocalizedString(data={
                    "ru":"По ФИО и адресу",
                    "en":"By full name and address"
                    }
                ),
                description=LocalizedString(data={
                    "ru":"описание стандартного метода отправки посылок почтой росиси",
                    "en":"на русском сначала блин давай"
                    }
                ),
                requirements=[
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"ФИО",
                            "en":"Full name"
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"пишите типо сюда свою Фамилию, Имя и Отчество лол",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    ),
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"Полный адрес",
                            "en":"Address"
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"При написании адреса не забудьте указать индекс, область, район, наименование населенного пункта и дальше змейка сам пиши я не ибу",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    )
                ]
            )           
        ]
    )
    
    cdek = DeliveryService(
        name=LocalizedString(data={
            "ru":"CDEK",
            "en":"CDEK"
            }
        ),
        requirements_options=[
            DeliveryRequirementsList(
                name=LocalizedString(data={
                    "ru":"По номеру телефона и адресу ПВЗ",
                    "en":""
                    }
                ),
                description=LocalizedString(data={
                    "ru":"описание чего-то там не знаю чего",
                    "en":"сначала на русском текст нормально надо"
                    }
                ),
                requirements=[
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"Номер телефона",
                            "en":"Phone number"
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"пишите номер в формате +7xxxxxxxxxx",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    ),
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"Полный адрес пункта выдачи",
                            "en":""
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"При написании адреса не забудьте перепроверить все ишак дражайший вы наш",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    )
                ]
            ) 
        ]
    )
    
    boxberry = DeliveryService(
        name=LocalizedString(data={
            "ru":"Boxberry",
            "en":"Boxberry"
            }
        ),
        requirements_options=[
            DeliveryRequirementsList(
                name=LocalizedString(data={
                    "ru":"По номеру телефона и адресу ПВЗ",
                    "en":""
                    }
                ),
                description=LocalizedString(data={
                    "ru":"описание чего-то там не знаю чего",
                    "en":"сначала на русском текст нормально надо"
                    }
                ),
                requirements=[
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"Номер телефона",
                            "en":"Phone number"
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"пишите номер в формате +7xxxxxxxxxx",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    ),
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"Полный адрес пункта выдачи",
                            "en":""
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"При написании адреса не забудьте перепроверить все ишак дражайший вы наш",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    )
                ]
            ) 
        ]
    )
    
    universal_international = DeliveryService(
        name=LocalizedString(data={
            "ru":"Универсальная",
            "en":"Universal"
            }
        ),
        is_foreign=True,
        requires_manual_confirmation=True,
        price=LocalizedMoney.empty_base(),
        requirements_options=[
            DeliveryRequirementsList(
                name=LocalizedString(data={
                    "ru":"По адресу, номеру и ФИО",
                    "en":""
                    }
                ),
                description=LocalizedString(data={
                    "ru":"описание чего-то там не знаю чего",
                    "en":"сначала на русском текст нормально надо"
                    }
                ),
                requirements=[
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"Адрес доставки",
                            "en":"Delivery address"
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"При написании адреса не забудьте перепроверить все ишак дражайший вы наш",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    ),
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"ФИО",
                            "en":"Full name"
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"пишите типо сюда свою Фамилию, Имя и Отчество лол",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    ),
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"Номер телефона",
                            "en":"Phone number"
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"пишите номер в формате +7xxxxxxxxxx",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    )
                ]
            )
        ]
    ) 
        
    
    ya_delivery = DeliveryService(
        name=LocalizedString(data={
            "ru":"Яндекс Доставка",
            "en":"Yandex Delivery"
            }
        ),
        requirements_options=[
            DeliveryRequirementsList(
                name=LocalizedString(data={
                    "ru":"По номеру телефона и адресу ПВЗ",
                    "en":""
                    }
                ),
                description=LocalizedString(data={
                    "ru":"описание чего-то там не знаю чего",
                    "en":"сначала на русском текст нормально надо"
                    }
                ),
                requirements=[
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"Номер телефона",
                            "en":"Phone number"
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"пишите номер в формате +7xxxxxxxxxx",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    ),
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"Полный адрес пункта выдачи",
                            "en":""
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"При написании адреса не забудьте перепроверить все ишак дражайший вы наш",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    )
                ]
            ) 
        ]
    )

    ozon_delivery = DeliveryService(
        name=LocalizedString(data={
            "ru":"Ozon Доставка",
            "en":"Ozon Delivery"
            }
        ),
        price=LocalizedMoney.from_keys(RUB=200.00, USD=3.00),
        requirements_options=[
            DeliveryRequirementsList(
                name=LocalizedString(data={
                    "ru":"По номеру телефона и адресу ПВЗ",
                    "en":""
                    }
                ),
                description=LocalizedString(data={
                    "ru":"описание чего-то там не знаю чего",
                    "en":"сначала на русском текст нормально надо"
                    }
                ),
                requirements=[
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"Номер телефона",
                            "en":"Phone number"
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"пишите номер в формате +7xxxxxxxxxx",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    ),
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"Полный адрес пункта выдачи",
                            "en":""
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"При написании адреса не забудьте перепроверить все ишак дражайший вы наш",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    )
                ]
            ) 
        ]
    )


    # await ctx.services.db.delivery_services.save(service)
    # await ctx.services.db.delivery_services.save(cdek)
    # await ctx.services.db.delivery_services.save(boxberry)
    await ctx.services.db.delivery_services.save(universal_international)
    # await ctx.services.db.delivery_services.save(ya_delivery)
    # await ctx.services.db.delivery_services.save(ozon_delivery)

@router.message(Command("add_additionals"))
async def add_additionals_handler(_, ctx: Context) -> None:
    additional = ProductAdditional(
        name=LocalizedString(data={
            "ru":"Страпон",
            "en":"DB PLACEHOLDER"}
        ),
        category="dildos",
        description=LocalizedString(data={
            "ru":"DB PLACEHOLDER",
            "en":"DB PLACEHOLDER"}
        ),
        price=LocalizedMoney.from_keys(RUB=400.00, USD=10.00),
        disallowed_products=[]
    )
    await ctx.services.db.additionals.save(additional)
    
    additional = ProductAdditional(
        name=LocalizedString(data={
            "ru":"Стержень",
            "en":"Стержень"}
        ),
        category="dildos",
        description=LocalizedString(data={
            "ru":"DB PLACEHOLDER",
            "en":"DB PLACEHOLDER"}
        ),
        price=LocalizedMoney.from_keys(RUB=400.00, USD=10.00),
        disallowed_products=[]
    )
    await ctx.services.db.additionals.save(additional)

