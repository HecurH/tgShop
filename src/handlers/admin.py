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
from schemas.types import LocalizedMoney, LocalizedString, LocalizedSavedMedia, LocalizedEntry, MediaPlaceholderLink
from ui.message_tools import list_commands

router = Router(name="admin")
middleware = RoleCheckMiddleware("admin")

router.message.middleware.register(middleware)
router.callback_query.middleware.register(middleware)


@router.message(Command("help"))
async def help_handler(_, ctx: Context):
    txt = "\n".join(doc for _, doc in list_commands(router))
    
    await ctx.message.answer(txt, parse_mode=None)
    
@router.message(Command("add_media_placeholder"))
async def add_media_placeholder_handler(_, ctx: Context, command: CommandObject):
    """/add_media_placeholder <photo/video/document>|<key>|<is_localized: true/false> - Добавить медиаплэйсхолдер"""
    args = command.args.split("|")
    if len(args) < 3:
        await ctx.message.answer(f"Недостаточно аргументов.")
        
    media_type = args[0]
    key = args[1]
    is_localized = args[2] == "true"
    
    if media_type not in ["photo","video","document"]:
        await ctx.message.answer(f"Неправильный тип медиа.")
        return
    if not is_localized:
        raw = await ctx.message.bot.download(ctx.message.document)

        msg_id = await ctx.message.answer_photo(photo=BufferedInputFile(
            raw.read(),
            filename=ctx.message.document.file_name
        )
        )
        media_id = getattr(msg_id, media_type)
        media_id = media_id[-1] if isinstance(media_id, list) else media_id
        media_id = media_id.file_id
        
        await ctx.services.db.media_placeholders.save(MediaPlaceholder(key=key, 
                                                                       value=LocalizedSavedMedia(media_type=getattr(MediaType, media_type), 
                                                                                                 media_id=media_id)
                                                                       )
                                                      )
        await ctx.message.answer(f"Медиаплэйсхолдер добавлен.")
        return
    
    await ctx.fsm.update_data(media_type=media_type, key=key, **{lang: None for lang in SUPPORTED_LANGUAGES_TEXT.values()})
    await call_state_handler(AdminStates.Main.GlobalMediaPlaceholders.SettingLocalizedMedia, ctx)

@router.message(Command("edit_media_placeholder"))
async def add_media_placeholder_handler(_, ctx: Context, command: CommandObject):
    """/edit_media_placeholder <photo/video/document>|<key>|<is_localized: true/false> - Изменить медиаплэйсхолдер"""
    args = command.args.split("|")
    if len(args) < 3:
        await ctx.message.answer(f"Недостаточно аргументов.")
        
    media_type = args[0]
    key = args[1]
    is_localized = args[2] == "true"
    
    if media_type not in ["photo","video","document"]:
        await ctx.message.answer(f"Неправильный тип медиа.")
        return
    if not is_localized:
        placeholder = await ctx.services.db.media_placeholders.find_by_key(key)
        if not placeholder:
            await ctx.message.answer(f"Медиаплэйсхолдер не найден.")
        
        raw = await ctx.message.bot.download(ctx.message.document)

        msg_id = await ctx.message.answer_photo(photo=BufferedInputFile(
            raw.read(),
            filename=ctx.message.document.file_name
        )
        )
        media_id = getattr(msg_id, media_type)
        media_id = media_id[-1] if isinstance(media_id, list) else media_id
        media_id = media_id.file_id
        
        placeholder.value = LocalizedSavedMedia(media_type=getattr(MediaType, media_type), 
                                                media_id=media_id)
        
        await ctx.services.db.media_placeholders.save(placeholder)
        await ctx.services.placeholders.update_placeholders()
        await ctx.message.answer(f"Медиаплэйсхолдер изменен.")
        return
    
    await ctx.fsm.update_data(media_type=media_type, key=key, **{lang: None for lang in SUPPORTED_LANGUAGES_TEXT.values()})
    await call_state_handler(AdminStates.Main.GlobalMediaPlaceholders.SettingLocalizedMedia, ctx)

@router.message(AdminStates.Main.GlobalMediaPlaceholders.SettingLocalizedMedia)
async def setting_localized_media_handler(_, ctx: Context):
    text = ctx.message.text
    if text == ctx.t.UncategorizedTranslates.cancel:
        await call_state_handler(CommonStates.MainMenu, ctx)
        return
    
    remaining_langs = [lang for lang in SUPPORTED_LANGUAGES_TEXT.values() 
                      if not await ctx.fsm.get_value(lang)]
    
    if remaining_langs:
        raw = await ctx.message.bot.download(ctx.message.document)

        msg_id = await ctx.message.answer_photo(photo=BufferedInputFile(
            raw.read(),
            filename=ctx.message.document.file_name
        )
        )
        
        media_id = getattr(msg_id, await ctx.fsm.get_value("media_type"))
        media_id = media_id[-1] if isinstance(media_id, list) else media_id
        media_id = media_id.file_id
        
        await ctx.fsm.update_data(**{remaining_langs[0]: media_id})
        
        if len(remaining_langs) > 1:
            await call_state_handler(AdminStates.Main.GlobalMediaPlaceholders.SettingLocalizedMedia, ctx)
            return
    
    langs_dict = {lang: await ctx.fsm.get_value(lang) for lang in SUPPORTED_LANGUAGES_TEXT.values()}
    key = await ctx.fsm.get_value("key")
    try:
        placeholder = await ctx.services.db.media_placeholders.find_by_key(key)
        if placeholder:
            placeholder.value = LocalizedSavedMedia(media_type=getattr(MediaType, await ctx.fsm.get_value("media_type")), 
                                                    media_id=langs_dict)
            
            await ctx.services.db.media_placeholders.save(placeholder)
        else:
        
            await ctx.services.db.media_placeholders.save(MediaPlaceholder(key=key, 
                                                                           value=LocalizedSavedMedia(media_type=getattr(MediaType, await ctx.fsm.get_value("media_type")), 
                                                                                                     media_id=langs_dict)
                                                                          )
                                                         )
        
        await ctx.services.placeholders.update_placeholders()
        await call_state_handler(CommonStates.MainMenu, ctx, send_before="Плейсхолдер установлен.")
        
    except Exception as e:
        raise Exception(f"Не удалось установить плейсхолдер: {e}")

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
    cat = Category(
        name="anal_plugs",
        localized_name=LocalizedString(data={
                "ru": "Анальные пробки",
                "en": "Anal plugs"
            }))
    await ctx.services.db.categories.save(cat)

    cat = Category(
        name="other",
        localized_name=LocalizedString(data={
                "ru": "Другое",
                "en": "Other"
            }))
    await ctx.services.db.categories.save(cat)


@router.message(Command("add_product"))
async def image_saving_handler(_, ctx: Context) -> None:
    configuration = ProductConfiguration(options={
        "size": ConfigurationOption(
            name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Size.name"),
            text=LocalizedEntry(path="ProductConfigurationTranslates.Options.Size.text"),
            chosen_key="medium",
            choices={
                "small": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Size.Choices.Small.name"),
                    media=LocalizedSavedMedia(
                        media_type=MediaType.photo,
                        media_id="AgACAgIAAxkDAAMnaQO9pmz7m-ygxnI1BNGvP7FtoHEAAhoFMhuHLSBIN73TQfbZTMABAAMCAAN5AAM2BA"
                    ),
                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Size.Choices.Small.description"),

                    price=LocalizedMoney.from_keys(RUB=-1500.00, USD=-30.00)
                ),
                "medium": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Size.Choices.Medium.name"),
                    media=LocalizedSavedMedia(
                        media_type=MediaType.photo,
                        media_id="AgACAgIAAxkDAAMqaQO9thReF1LgxZQ8FIpJH3HnzhwAAhsFMhuHLSBIIaPS4-7Vxd0BAAMCAAN5AAM2BA"
                    ),
                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Size.Choices.Medium.description")
                ),
                "large": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Size.Choices.Large.name"),
                    media=LocalizedSavedMedia(
                        media_type=MediaType.photo,
                        media_id="AgACAgIAAxkDAAMtaQO9yVk9QKXrhzxvJtBaf4lJ-EcAAhwFMhuHLSBIYTDE_oitamIBAAMCAAN5AAM2BA"
                    ),
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
                    media=MediaPlaceholderLink(placeholder_key="firmness_gradation_choice"),
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
                    media=LocalizedSavedMedia(media_type=MediaType.photo, 
                                              media_id={"ru": "AgACAgIAAxkDAAM2aQO-fg3Anx3Sa1tL8ccry-Lim_EAAiIFMhuHLSBIPwf7eqM0xUYBAAMCAAN3AAM2BA",
                                                        "en": "AgACAgIAAxkDAAM5aQO-jZm4zRcldXLf_xNMeT-mRpsAAiMFMhuHLSBIcybdSYdcmF4BAAMCAAN3AAM2BA"
                                                        }),
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
                    media=MediaPlaceholderLink(placeholder_key="existing_color_choice"),
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
                    media=MediaPlaceholderLink(placeholder_key="two_zone_color_choice"),
                    is_custom_input=True,

                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.TwoZone.description"),
                ),
                "three-zone": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.ThreeZone.name"),
                    media=MediaPlaceholderLink(placeholder_key="three_zone_color_choice"),
                    is_custom_input=True,
                    price=LocalizedMoney.from_keys(RUB=500.00, USD=10.00),

                    description=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.ThreeZone.description")
                ),
                "swirl": ConfigurationChoice(
                    name=LocalizedEntry(path="ProductConfigurationTranslates.Options.Color.Choices.Swirl.name"),
                    media=MediaPlaceholderLink(placeholder_key="swirl_color_choice"),
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
                    media=MediaPlaceholderLink(placeholder_key="available_colors"),
                )
            }
        )
    })

    product = Product(
        name=LocalizedString(data={
            "ru":"Дракон Хайден",
            "en":"Hiden Dragon"}
        ),
        name_for_tax="Индивидуальная отливка силиконового изделия \"Дракон Хайден\"",
        category="dildos",
        short_description_media=LocalizedSavedMedia(
            media_type=MediaType.photo,
            media_id="AgACAgIAAxkDAAMhaQO9QWtmr-kYeTnZ19vJ-MN4j4wAAhYFMhuHLSBItbZmbg0sU5ABAAMCAAN3AAM2BA"
        ),
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
        long_description_media=LocalizedSavedMedia(
            media_type=MediaType.photo,
            media_id="AgACAgIAAxkDAAMkaQO9h8CJpyYTPdsJbXIYxwQn1FEAAhgFMhuHLSBI9M6B5_SAJUwBAAMCAAN3AAM2BA"
        ),
        base_price=LocalizedMoney.from_keys(RUB=6000.00, USD=100.00),
        configuration=configuration,
        configuration_media=LocalizedSavedMedia(
            media_type=MediaType.photo,
            media_id="AgACAgIAAxkDAAMkaQO9h8CJpyYTPdsJbXIYxwQn1FEAAhgFMhuHLSBI9M6B5_SAJUwBAAMCAAN3AAM2BA"
        )
    )

    await ctx.services.db.products.save(product)


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

