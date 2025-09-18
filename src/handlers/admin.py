import datetime
import json
import re
from aiogram.fsm.context import FSMContext

from aiogram import F, Router
from aiogram.filters import CommandObject, Command, CommandStart
from aiogram.types import Message, BufferedInputFile
from pydantic import ValidationError
from pydantic_mongo import PydanticObjectId

from core.services.db import *

from core.helper_classes import Context
from core.middlewares import RoleCheckMiddleware
from core.states import AdminStates, CommonStates, call_state_handler
from schemas.enums import OrderStateKey
from schemas.types import LocalizedMoney, LocalizedString
from ui.message_tools import list_commands

router = Router(name="admin")
middleware = RoleCheckMiddleware("admin")

router.message.middleware.register(middleware)
router.callback_query.middleware.register(middleware)


@router.message(Command("help"))
async def help_handler(_, ctx: Context):
    txt = "\n".join(f"{cmd} - {doc}" for cmd, doc in list_commands(router))
    
    await ctx.message.answer(txt)

@router.message(Command("msg_to"))
async def msg_to_handler(_, ctx: Context, command: CommandObject):
    """/msg_to <user_id>"""
    user_id = int(command.args) if command.args.isdigit() else None
    if not user_id:
        await ctx.message.answer("Неправильный формат команды")
        return
    
    customer = await ctx.services.db.customers.find_customer_by_user_id(user_id)
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
    cart_entries = await ctx.services.db.cart_entries.get_entries_by_order(order)
    
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
    await call_state_handler(CommonStates.MainMenu, ctx, send_before=("Заказ подтвержден", 1))
    
@router.message(Command("unform_order"))
async def unform_order_handler(_, ctx: Context, command: CommandObject):
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
    cart_entries = await ctx.services.db.cart_entries.get_entries_by_order(order)
    await ctx.services.db.orders.delete(order)
    for entry in cart_entries:
        entry.order_id = None
        entry.frozen_product = None
    
    await ctx.services.db.cart_entries.save_many(cart_entries)
    
    await ctx.services.db.customers.add_bonus_money(customer, order.price_details.bonuses_applied)
    if order.promocode_id:
        await ctx.services.db.promocodes.update_usage(order.promocode_id, -1)
        
    await call_state_handler(CommonStates.MainMenu, ctx, send_before=("Успешно.", 1))

@router.message(Command("confirm_order_price"))
async def admin_confirm_price_handler(_, ctx: Context, command: CommandObject):
    order_id: str = command.args
    order = await ctx.services.db.orders.find_one_by_id(PydanticObjectId(order_id)) if order_id else None
    if not order:
        await ctx.message.answer("Заказ не найден")
        return
    
    entries = list(await ctx.services.db.cart_entries.get_price_confirmation_entries(order))
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
    
    cart_entries = list(await ctx.services.db.cart_entries.get_price_confirmation_entries(order))
    
    for idx, cart_entry in enumerate(cart_entries):
        updater_entry = entries[idx]
        for key, price in updater_entry.items():
            chosen = cart_entry.configuration.options[key].get_chosen()
            chosen.price = price
        
        cart_entry.configuration.price_confirmed_override = True
        cart_entry.configuration.update_price()
        
    order.state.set_state(OrderStateKey.waiting_for_forming)
    
    products_price = await ctx.services.db.cart_entries.calculate_cart_entries_price_by_order(order)
    order.price_details = OrderPriceDetails.new(customer, products_price)
    
    await ctx.services.db.cart_entries.save_many(cart_entries)
    await ctx.services.db.orders.save(order)
    
    await ctx.services.notificators.UserTelegramNotificator.send_order_price_confirmed(customer)
    await call_state_handler(CommonStates.MainMenu, ctx, send_before=("Цена подтверждена.", 1))
    
#command like /manual_delivery_price <user_id> <delivery_service_id> <req_options_list_idx> <json dumped list of securs> <serialized LocalizedMoney>
@router.message(Command("manual_delivery_price"))
async def manual_delivery_price_handler(_, ctx: Context, command: CommandObject):
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
        

@router.message(Command("save_image"))
async def image_saving_handler(_, ctx: Context):
    raw = await ctx.message.bot.download(ctx.message.document)

    msg_id = await ctx.message.answer_photo(photo=BufferedInputFile(
        raw.read(),
        filename="image.jpg"
    )
    )
    await ctx.message.answer(msg_id.photo[-1].file_id)

@router.message(Command("save_video"))
async def image_saving_handler(_, ctx: Context):
    raw = await ctx.message.bot.download(ctx.message.document)

    msg_id = await ctx.message.answer_video(video=BufferedInputFile(
        raw.read(),
        filename="image.mp4"
    )
    )
    await ctx.message.answer(msg_id.video.file_id)

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
            name=LocalizedString(data={
                "ru": "Размер",
                "en": "Size"
            }),
            text=LocalizedString(data={
                "ru": "Выберите размер изделия:",
                "en": "Choose the size of the product:"
            }),
            chosen="medium",
            choices={
                "small": ConfigurationChoice(
                    label=LocalizedString(data={"ru":"Маленький", "en":"Small"}),
                    photo_id="AgACAgIAAxkDAAIEvmgdCZ7FHIjc4ZWxlEr1-RKo4mamAALx8zEb4TjpSMnWZTFndXzfAQADAgADeQADNgQ",
                    description=LocalizedString(data={
                        "ru": "Выбран <b>Маленький</b> размер.\n\nУвидеть значения выбранного размера изделия можно на прикрепленном фото.",
                        "en": "Selected <b>Small</b> size.\n\nYou can see all the size values in the attached picture."}),

                    price=LocalizedMoney.from_dict({"RUB":-1000.00, "USD":-30.00})
                ),
                "medium": ConfigurationChoice(
                    label=LocalizedString(data={"ru":"Средний", "en":"Medium"}),
                    photo_id="AgACAgIAAxkDAAIEuWgdAVwm5m-WAtrHRu_LZrlvUa-MAAKS8zEb4TjpSHff2pId4ujoAQADAgADeQADNgQ",
                    description=LocalizedString(data={
                        "ru": "Выбран <b>Средний</b> размер.\n\nУвидеть значения выбранного размера изделия можно на прикрепленном фото.",
                        "en": "Selected <b>Medium</b> size.\n\nYou can see all the size values in the attached picture."})
                ),
                "big": ConfigurationChoice(
                    label=LocalizedString(data={"ru":"Большой", "en":"Big"}),
                    photo_id="AgACAgIAAxkDAAIEwmgdCcaeJbdRNP39SPUifkgCY0T1AAL28zEb4TjpSODUEAABvCEBnAEAAwIAA3kAAzYE",
                    description=LocalizedString(data={
                        "ru": "Выбран <b>Большой</b> размер.\n\nУвидеть значения выбранного размера изделия можно на прикрепленном фото.",
                        "en": "Selected <b>Big</b> size.\n\nYou can see all the size values in the attached picture."}),

                    price=LocalizedMoney.from_dict({"RUB":1000.00, "USD":30.00})
                )
            }
        ),
        "firmness": ConfigurationOption(
            name=LocalizedString(data={
                "ru": "Мягкость",
                "en": "Firmness"
            }),
            text=LocalizedString(data={
                "ru": "Выберите мягкость изделия:",
                "en": "Choose the firmness of the product:"
            }),
            chosen="medium",
            choices={
                "soft": ConfigurationChoice(
                    label=LocalizedString(data={"ru": "Мягкий", "en": "Soft"}),
                    video_id="BAACAgIAAxkDAAIEtGgc93O_W9FxMWJ7D859YU2tP9fxAAJGdwAC4TjpSKfM23poBFmlNgQ",
                    description=LocalizedString(data={
                        "ru": "Выбран <b>Мягкий</b> силикон.\n\nПример можно увидеть в прикрепленном к сообщению видео.",
                        "en": "<b>Soft</b> silicone is selected.\n\nYou can see an example in the attached video."})
                ),
                "medium": ConfigurationChoice(
                    label=LocalizedString(data={"ru": "Средний", "en": "Medium"}),
                    video_id="BAACAgIAAxkDAAIEtGgc93O_W9FxMWJ7D859YU2tP9fxAAJGdwAC4TjpSKfM23poBFmlNgQ",
                    description=LocalizedString(data={
                        "ru": "Выбран силикон <b>Средней</b> мягкости.\n\nПример можно увидеть в прикрепленном к сообщению видео.",
                        "en": "<b>Medium-soft</b> silicone is selected.\n\nYou can see an example in the attached video."})
                ),
                "firm": ConfigurationChoice(
                    label=LocalizedString(data={"ru": "Твёрдый", "en": "Firm"}),
                    video_id="BAACAgIAAxkDAAIEtGgc93O_W9FxMWJ7D859YU2tP9fxAAJGdwAC4TjpSKfM23poBFmlNgQ",
                    description=LocalizedString(data={
                        "ru": "Выбран <b>Твёрдый</b> силикон.\n\nПример можно увидеть в прикрепленном к сообщению видео.",
                        "en": "<b>Firm</b> silicone is selected.\n\nYou can see an example in the attached video."})
                ),
                "firmness_gradation": ConfigurationChoice(
                    label=LocalizedString(data={"ru": "Градация жёсткости", "en": "Firmness gradation"}),
                    video_id="BAACAgIAAxkDAAIEtGgc93O_W9FxMWJ7D859YU2tP9fxAAJGdwAC4TjpSKfM23poBFmlNgQ",
                    is_custom_input=True,
                    can_be_blocked_by=["color/swirl"],

                    description=LocalizedString(data={
                        "ru": "на картинке типо дилдак с полосами, разделяющими зоны, и юзер типо расписывает, - (кнот мягкий, кончик и основание средние)",
                        "en": "The picture shows a dildo with stripes dividing zones, and the user can specify, for example: (knot - soft, the rest are medium)."
                    }),
                    price=LocalizedMoney.from_dict({"RUB":400.00, "USD":6.00})

                )
            }
        ),
        "color": ConfigurationOption(
            name=LocalizedString(data={
                "ru": "Окрас",
                "en": "Color"
            }),
            text=LocalizedString(data={
                "ru": "Что вы хотите сделать?",
                "en": "What do you want to do?"
            }),
            chosen="sel_existing",
            choices={
                "sel_existing": ConfigurationChoice(
                    label=LocalizedString(data={"ru": "Существующий", "en": "Existing one"}),
                    video_id="BAACAgIAAxkDAAIEtGgc93O_W9FxMWJ7D859YU2tP9fxAAJGdwAC4TjpSKfM23poBFmlNgQ",
                    existing_presets=True,
                    existing_presets_chosen=1,
                    existing_presets_quantity=3,

                    description=LocalizedString(data={
                        "ru": "Вы выбрали раскраску под номером {chosen}.",
                        "en": "You have chosen the color number {chosen}."})
                ),
                "two-zone": ConfigurationChoice(
                    label=LocalizedString(data={"ru": "Двухзонный", "en": "Two-zone"}),
                    video_id="BAACAgIAAxkDAAIEtGgc93O_W9FxMWJ7D859YU2tP9fxAAJGdwAC4TjpSKfM23poBFmlNgQ",
                    is_custom_input=True,

                    description=LocalizedString(data={
                        "ru": "Выберите цвета для двух зон: кончик и основание. Просто напишите, какой цвет хотите для каждой части. Если хотите шиммер, блёстки, люминофор или градиент (2 зоны) — не забудьте выбрать их в разделе «Дополнительно».",
                        "en": "Choose colors for the two zones: tip and base. Just write which color you want for each part. If you want shimmer, glitter, phosphor, or a gradient for one of the zones — don't forget to select them in the 'Additional' section."
                    })
                ),
                "three-zone": ConfigurationChoice(
                    label=LocalizedString(data={"ru": "Трёхзонный", "en": "Three-zone"}),
                    video_id="BAACAgIAAxkDAAIEtGgc93O_W9FxMWJ7D859YU2tP9fxAAJGdwAC4TjpSKfM23poBFmlNgQ",
                    is_custom_input=True,

                    description=LocalizedString(data={
                        "ru": "Выберите цвета для каждой из трёх зон: кончик, узел и основание. Просто напишите, какой цвет хотите для каждой части. Если хотите шиммер, блёстки, люминофор или градиент (2 зоны) — не забудьте выбрать их в разделе «Дополнительно».",
                        "en": "Choose colors for each of the three zones: tip, knot, and base. Just write which color you want for each part. If you want shimmer, glitter, or phosphor, don't forget to select them in the 'Additional' section."
                    })
                ),
                "swirl": ConfigurationChoice( # вихревая, пользователю надо уточнить до трех цветов для этого
                    label=LocalizedString(data={"ru": "Вихрь", "en": "Swirl"}),
                    video_id="BAACAgIAAxkDAAIEtGgc93O_W9FxMWJ7D859YU2tP9fxAAJGdwAC4TjpSKfM23poBFmlNgQ",
                    is_custom_input=True,
                    can_be_blocked_by=["firmness/firmness_gradation"],
                    price=LocalizedMoney.from_dict({"RUB":500.00, "USD":10.00}),

                    description=LocalizedString(data={
                        "ru": "Выберите до трёх цветов для вихревой раскраски. Просто напишите, какие цвета хотите смешать. Если хотите шиммер, блёстки или люминофор — не забудьте выбрать их в разделе «Дополнительно».",
                        "en": "Choose up to three colors for the swirl coloring. Just write which colors you want to mix. If you want shimmer, glitter, or phosphor, don't forget to select them in the 'Additional' section."
                    })
                ),
                "own_colors": ConfigurationChoice(
                    label=LocalizedString(data={"ru": "Своя раскраска", "en": "Custom colors"}),
                    video_id="BAACAgIAAxkDAAIEtGgc93O_W9FxMWJ7D859YU2tP9fxAAJGdwAC4TjpSKfM23poBFmlNgQ",
                    is_custom_input=True,
                    blocks_price_determination=True,

                    description=LocalizedString(data={
                        "ru": "Здесь типо текст где\nэээээ\nну типо тут то что можно менять/какие цвета, цены на них же ээ да",
                        "en": "Here's like a text where\nuhhhhh\n I'm like here's what you can change/what colors, the prices for them are the same, uh yes"})
                ),
                "additional": ConfigurationSwitches(
                    label=LocalizedString(data={"ru": "Дополнительно", "en": "Additional"}),
                    video_id="BAACAgIAAxkDAAIEtGgc93O_W9FxMWJ7D859YU2tP9fxAAJGdwAC4TjpSKfM23poBFmlNgQ",
                    description=LocalizedString(data={
                        "ru": "Тут чисто инфа про сами свитчи",
                        "en": "Тут чисто инфа про сами свитчи"}),
                    switches=[
                        ConfigurationSwitch(
                            name=LocalizedString(data={"ru": "Градиент", "en": "Gradient"}),
                            price=LocalizedMoney.from_dict({"RUB":100.00, "USD":6.00})

                        ),
                        ConfigurationSwitch(
                            name=LocalizedString(data={"ru": "Блёстки", "en": "Glitter"}),
                            price=LocalizedMoney.from_dict({"RUB":100.00, "USD":6.00})

                        ),
                        ConfigurationSwitch(
                            name=LocalizedString(data={"ru": "Шиммер", "en": "Shimmer"}),
                            price=LocalizedMoney.from_dict({"RUB": 100.00, "USD": 6.00})

                        ),
                        ConfigurationSwitch(
                            name=LocalizedString(data={"ru": "Люминофор", "en": "Phosphor"}),
                            price=LocalizedMoney.from_dict({"RUB": 100.00, "USD": 6.00})

                        )
                    ]
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
        short_description=LocalizedString(data={
            "ru":"Заглушка хд",
            "en":"Заглушка хд"}
        ),
        short_description_photo_id="AgACAgIAAxkDAAIEqmgc2mt5nYStZBhwifMHuicCdPk5AAJo8TEb4TjpSPRjXA9O3dgSAQADAgADeQADNgQ",
        long_description=LocalizedString(data={
            "ru":"""<blockquote expandable>Нежное сияние пурпурной драконьей чешуи под лучами алого заката. Хайден всегда знает, как позаботиться о своём любимом партнёре. Мягко обхватывая тебя своими опытными лапками, чутко лаская чувствительные зоны, он приближается всё ближе и ближе, заставляя твоё тело легко подрагивать от возбуждения. Он улавливает твоё сбитое дыхание, чуть улыбаясь от удовольствия... 

Его кончик нежно входит в тебя, заставляя постанывать и дрожать еще сильнее. Постепенно расширяясь, мягко входят сплетения, доходя до окончательно добивающего узла... 
Сильный и нежный, дракон Хайден будет идеальным партнёром, дарящим мягкие ласки и доминирущее превосходство, ведь все бурные фантазии, воплощаемые в жизнь, зависят только от твоего желания~</blockquote>

Присоска идет в комплекте!""",
            "en":"Hiden Dragon"}
        ),
        long_description_photo_id="AgACAgIAAxkDAAIEqmgc2mt5nYStZBhwifMHuicCdPk5AAJo8TEb4TjpSPRjXA9O3dgSAQADAgADeQADNgQ",
        base_price=LocalizedMoney.from_dict({
            "RUB": 5000.00,
            "USD": 100.00
        }),
        configuration_photo_id="AgACAgIAAxkDAAIEqmgc2mt5nYStZBhwifMHuicCdPk5AAJo8TEb4TjpSPRjXA9O3dgSAQADAgADeQADNgQ",
        configuration=configuration
    )

    await ctx.services.db.products.save(product)


@router.message(Command("add_addit"))
async def addit(message: Message, command: CommandObject, state: FSMContext, db: DatabaseService, lang: str) -> None:
    additional = ProductAdditional(
        name=LocalizedString(data={
            "ru":"Дракон Хайден",
            "en":"Hiden Dragon"}
        ),
        category="dildos",
        short_description=LocalizedString(data={
            "ru":"Заглушка хд",
            "en":"Заглушка хд"}
        ),
        price=LocalizedMoney.from_dict({"RUB": 1000, "USD": 10})
    )

    await db.additionals.save(additional)
    
@router.message(Command("delete_acc"))
async def addit(message: Message, command: CommandObject, ctx: Context) -> None:
    await ctx.services.db.customers.delete(ctx.customer)
    
@router.message(Command("add_delivery_services"))
async def addit(message: Message, command: CommandObject, ctx: Context) -> None:
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
        price=LocalizedMoney.from_dict({"RUB": 0,"USD": 0}),
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
        price=LocalizedMoney.from_dict({
            "RUB": 200,
            "USD": 3
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


    # await ctx.db.delivery_services.save(service)
    # await ctx.db.delivery_services.save(cdek)
    # await ctx.db.delivery_services.save(boxberry)
    await ctx.services.db.delivery_services.save(universal_international)
    # await ctx.db.delivery_services.save(ya_delivery)
    # await ctx.db.delivery_services.save(ozon_delivery)

@router.message(Command("add_additionals"))
async def add_additionals_handler(message: Message, command: CommandObject, state: FSMContext, db: DatabaseService, lang: str) -> None:
    additional = ProductAdditional(
        name=LocalizedString(data={
            "ru":"Страпон",
            "en":"DB PLACEHOLDER"}
        ),
        category="dildos",
        short_description=LocalizedString(data={
            "ru":"DB PLACEHOLDER",
            "en":"DB PLACEHOLDER"}
        ),
        price=LocalizedMoney.from_dict({"RUB": 400, "USD": 10}),
        disallowed_products=[]
    )
    await db.additionals.save(additional)
    
    additional = ProductAdditional(
        name=LocalizedString(data={
            "ru":"Стержень",
            "en":"Стержень"}
        ),
        category="dildos",
        short_description=LocalizedString(data={
            "ru":"DB PLACEHOLDER",
            "en":"DB PLACEHOLDER"}
        ),
        price=LocalizedMoney.from_dict({"RUB": 400, "USD": 10}),
        disallowed_products=[]
    )
    await db.additionals.save(additional)

