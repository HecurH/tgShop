import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import json
from typing import Iterable, Optional
from aiogram import html
from bson import Decimal128

from registry.payments import SUPPORTED_PAYMENT_METHODS
from core.helper_classes import Context
from schemas.db_models import *
from core.types.enums import CartItemSource, DiscountType, InviterType, OrderStateKey
from core.types.values import LocalizedMoney
from ui.message_tools import build_list


def gen_product_configurable_info_text(
    configuration: ProductConfiguration,
    ctx: Context
) -> str:
    options = configuration.options
    currency = ctx.customer.currency
    
    def gen_price_info(price: LocalizedMoney):
        sign = "+" if price.get_amount(currency) > 0 else ""
        return f"{sign}{price.to_text(currency)}"
    
    def generate_option_description(option: ConfigurationOption) -> str:
        conf_choice = option.get_chosen()
        # price = option.calculate_price()
        
        name = conf_choice.name.get(ctx)
        
        presets = f" ({conf_choice.existing_presets_chosen})" if conf_choice.existing_presets and conf_choice.existing_presets_chosen else ""
        
        price_info = f" {gen_price_info(conf_choice.price)}" if conf_choice.price.get_amount(currency) != 0 else ""
        # if len(option.get_switches()) > 1 or price.get_amount(currency) != 0:
        #     price_info = f" {gen_price_info(price)}"
            
        custom = f" — \n<blockquote expandable>{html.quote(conf_choice.custom_input_text)}</blockquote>" if conf_choice.is_custom_input and conf_choice.custom_input_text else ""
        
        value = f"{name}{presets}{price_info}{custom}"
        selected_options = f"{option.name.get(ctx)}: {value}"
        
        for choice in option.choices.values():
            if not isinstance(choice, ConfigurationSwitches):
                continue
            
            enabled_switches = choice.get_enabled()
            if not enabled_switches: 
                continue
            
            def switch_text(switch):
                name = switch.name.get(ctx)
                return f"{name} {gen_price_info(switch.price)}"
            
            switches_text = "\n"
            switches_text += build_list([switch_text(switch) for switch in enabled_switches], padding=2)
            selected_options += switches_text
        return selected_options
    
    selected_options = build_list([generate_option_description(option) for option in options.values()], '▫️', 0)

    if additionals := configuration.additionals:
        price = configuration.calculate_additionals_price()
        add_price = f" ({price.to_text(currency)})" if price.get_amount(currency) > 0 and len(additionals) > 1 else ""
        selected_options += f"\n\n➕ {ctx.t.AssortmentTranslates.additionals}{add_price}:\n"
        
        def gen_additional_text(additional):
            name = additional.name.get(ctx)
            price = additional.price
            price_text = price.to_text(currency)
            price_info = f"+{price_text}" if price.get_amount(currency) > 0 else price.to_text(currency)
            return f"{name} {price_info}"
        
        selected_options += build_list([gen_additional_text(additional) for additional in additionals], '•', 2)

    return f"{ctx.t.AssortmentTranslates.currently_selected}\n{selected_options}" if selected_options else ""

async def form_entry_description(entry: CartEntry, ctx):
    is_product = entry.source_type == CartItemSource.product
    
    product: Product = await ctx.services.db.products.find_one_by_id(entry.source_id) if is_product else None
    
    quantity_text = f" {entry.quantity} {ctx.t.UncategorizedTranslates.unit(entry.quantity)}" if entry.quantity > 1 else ""
    price = (product.price + entry.configuration.price) if is_product else entry.frozen_snapshot.price
    price_text = price.to_text(ctx.customer.currency)
    price_text = f"{price_text} * {entry.quantity} = {(price*entry.quantity).to_text(ctx.customer.currency)}" if entry.quantity != 1 else price_text
    
    return f"{product.name.get(ctx) if product else entry.frozen_snapshot.name.get(ctx)}{quantity_text} — {price_text}"


class AdminTextGen:
    @staticmethod
    async def customer_menu_text(customer: Customer, ctx: Context):
        inviter = await ctx.services.db.inviters.find_by_customer_id(customer.id)
        invited = inviter.invited_customers if inviter else 0
        invited_list = await ctx.services.db.customers.find_many_by_inviter_id(inviter.id) if inviter else []
        
        invited_orders = inviter.invited_customers_first_orders if inviter else 0
        
        def delivery_info(delivery_info: DeliveryInfo):
            service = delivery_info.service
        
            requirements = service.selected_option.requirements
            
            requirements_info_text = "\n".join([f"  {requirement.name.get(ctx)}: <tg-spoiler>{html.quote(requirement.value.get())}</tg-spoiler>" for requirement in requirements])
            return ("Способ доставки: {delivery_service} ({service_price}), {delivery_req_lists_name}\n{requirements}").format(delivery_service=service.name.get(ctx), service_price=service.price.to_text(ctx.customer.currency), delivery_req_lists_name=service.selected_option.name.get(ctx), requirements=requirements_info_text)
        
        async def orders_info():
            orders = await ctx.services.db.orders.find_customer_orders(customer)
            if len(orders) == 0:
                return "Нету."
            txt = ""
            for order in orders:
                txt += f"\n🛒 {order.id} — {order.state.get_localized_name(ctx.lang)} — {order.price_details.total_price.to_text()}"
            return txt
            
            
        
        text = f"""👤 <a href=\"tg://user?id={customer.user_id}\">{customer.user_id}</a>

Приглашён: {(await ctx.services.db.inviters.find_one_by_id(customer.invited_by)).customer_id if customer.invited_by else 'Никем'}
Зарегистрировался: {customer.id.generation_time.strftime("%d.%m.%Y %H:%M")} UTC
Заблокировал бота? {customer.kicked}
Заблокирован? {customer.banned}

Язык: {customer.lang}
Валюта: {customer.currency}

На бонусном счету {customer.bonus_wallet.to_text()}

Доставка: {delivery_info(customer.delivery_info) if customer.delivery_info else 'Нет'}
Она ждет подтверждения стоимости? {customer.waiting_for_manual_delivery_info_confirmation}

Скольких пригласил: {invited} 
[{', '.join([str(c.user_id) for c in invited_list])}]

Из них сделали хоть один заказ: {invited_orders}

Заказы: {await orders_info()}
"""
        return text
    
    @staticmethod
    async def active_orders_menu_text(ctx: Context):
        active_orders = await ctx.services.db.orders.find_by({"state.key": {"$ne": OrderStateKey.received}})
        
        text = ""
        for order in active_orders:
            text += f"<b>Заказ <code>{order.id}</code></b> от {order.id.generation_time.strftime('%d.%m.%Y %H:%M UTC')}\n"
            text += f"  Статус заказа: {order.state.get_localized_name(ctx.lang)}\n"
            entries = await ctx.services.db.cart_entries.find_entries_by_order(order)
            products = await ctx.services.db.products.find_by({"_id": {"$in": [entry.source_id for entry in entries if entry.source_type == CartItemSource.product]}})
            names = [pr.name.get(ctx) for pr in products]
            names.extend(
                ent.frozen_snapshot.name.get(ctx)
                for ent in entries
                if ent.source_type == CartItemSource.discounted
            )
            
            entries_text = ", ".join(names)
            
            text += f"  Содержимое: {entries_text}\n\n"
            
        return text
    
    @staticmethod
    async def order_menu_text(order: Order, ctx: Context):
        customer = await ctx.services.db.customers.find_one_by_id(order.customer_id)
        order_viewing_menu = """<b>Заказ {order_id}</b> от {order_forming_date}, <a href=\"tg://user?id={user_id}\">покупатель</a> ({user_id})
{order_entries_description}        

Статус заказа: {order_status}{delivery_info}{payment_method}{promocode_info}{bonus_money_info}

Суммарная стоимость товаров: {products_price}
{price_info}
"""

        entries_description = ""
        entries = await ctx.services.db.cart_entries.find_entries_by_order(order)
        
        products = await ctx.services.db.products.find_by_entries(entries)
        products_dict = {product.id: product for product in products}

        for idx, entry in enumerate(entries):
            if entry.source_type == CartItemSource.product and (product := products_dict.get(entry.source_id)):
                amount_price = f"{entry.quantity} шт. — {entry.calculate_price(product).to_text('RUB')}" if entry.quantity > 1 else entry.calculate_price(product).to_text('RUB')
                
                entries_description += f"{idx+1} ({amount_price}): {product.name.get('ru')}:\n{gen_product_configurable_info_text(entry.configuration, ctx)}\n\n"
            elif entry.source_type == CartItemSource.discounted:
                entries_description += f"{idx+1} ({entry.calculate_price().to_text('RUB')}): {entry.frozen_snapshot.name.get('ru')}:\n{entry.frozen_snapshot.description.get('ru')}\n\n"
                
        delivery_info = order.delivery_info
        delivery_description = ""
        if delivery_info:
            delivery_description = f"{delivery_info.service.name.get(ctx)} — {order.price_details.delivery_price.to_text()}\n"
            delivery_description += build_list([f"{requirement.name.get(ctx)} - <tg-spoiler><code>{requirement.value.get()}</code></tg-spoiler>" for requirement in delivery_info.service.selected_option.requirements],
                                                    padding=2)
        
        if order.state == OrderStateKey.waiting_for_price_confirmation:
            price_info = ctx.t.OrdersTranslates.waiting_for_price_confirmation_info
        else:
            price_info = ctx.t.OrdersTranslates.total_price_info.format(total_price=order.price_details.total_price.to_text())
            
        promocode = await ctx.services.db.promocodes.find_one_by_id(order.promocode_id) if order.promocode_id else None
        promocode_info = ctx.t.CartTranslates.OrderConfiguration.promocode_info.format(code=promocode.code, 
                                                                                           discount=order.price_details.promocode_discount.to_text(),
                                                                                           description=promocode.description.get(ctx)) if promocode else None
        
        bonus_money_info = f"{order.price_details.bonuses_applied.to_text()}" if order.price_details.bonuses_applied else None
        
        return order_viewing_menu.format(order_id=str(order.id),
                                         user_id=customer.user_id,
                                        order_forming_date=order.id.generation_time.strftime("%d.%m.%Y %H:%M UTC"),
                                        order_entries_description=entries_description,
                                        order_status=order.state.get_localized_name(ctx.lang),
                                        delivery_info=ctx.t.OrdersTranslates.delivery_info.format(info=delivery_description) if delivery_info else "",
                                        payment_method=ctx.t.OrdersTranslates.payment_method.format(info=order.payment_method.name.get(ctx)) if order.payment_method else "",
                                        promocode_info=ctx.t.OrdersTranslates.promocode_info.format(info=promocode_info) if promocode else "",
                                        bonus_money_info=ctx.t.OrdersTranslates.bonus_money_info.format(info=bonus_money_info) if bonus_money_info else "",
                                        products_price=order.price_details.products_price.to_text(),
                                        price_info=price_info
                                        )
    
    
    @staticmethod
    def price_confirmation_text(entries: list[CartEntry], ctx: Context):
        
        entries_desc = "\n".join(f"{idx} — {entry.frozen_snapshot.name.get('ru')}: {gen_product_configurable_info_text(entry.configuration, ctx)}\nПолная стоимость: {(entry.calculate_price(entry.frozen_snapshot)).to_text_all()};" for idx, entry in enumerate(entries))
        next_input_info = "\n".join(f"{idx}: {json.dumps([{key: option.get_chosen().price.model_dump()}for key, option in entry.configuration.get_price_blocking_options().items()], ensure_ascii=False, default=lambda o: float(o if isinstance(o, Decimal) else o.to_decimal()) if isinstance(o, (Decimal, Decimal128)) else o)}" for idx, entry in enumerate(entries))


        return f"{entries_desc}\n\nИзмени цену конфигурации для товаров относительно их айди\n\n<code>{next_input_info}</code>"
    
    @staticmethod
    async def all_promocodes_text(ctx: Context):
        promocodes_list = await ctx.services.db.promocodes.get_all()
        text = ""
        for promocode in promocodes_list:
            text += f"\n🎟️ Код: {promocode.code}\n"
            
            expires_formated = promocode.expire_date.strftime("%d.%m.%Y %H:%M") if promocode.expire_date else None
            expired = " (истек)" if expires_formated and datetime.now(timezone.utc)  > promocode.expire_date else ""
            
            used_text = f" {promocode.already_used}/{promocode.max_usages}" if promocode.max_usages != -1 else f" {promocode.already_used}"
            
            ll = [
                f"➝ Скидка:{f' {promocode.discount.value.to_text_all()}' if promocode.discount.dicount_type == DiscountType.fixed else f' {promocode.discount.value}%' if promocode.discount.dicount_type == DiscountType.percent else ''}",
                ("📌 Только для новичков" if promocode.only_newbies else "📌 Для всех пользователей"),
                (f"⏳ Действует до: {expires_formated}{expired}" if expires_formated else "⏳ Неограниченно"),
                (f"🔢 Использовано: {used_text}")
            ]
            
            text += build_list(ll, before="")
        
        return text
    
    @staticmethod
    async def all_placeholders_text(ctx: Context):
        placeholders_list = await ctx.services.db.placeholders.get_all()
        text = ""
        for placeholder in placeholders_list:
            texts = build_list([f'{lang}: {txt}' for lang, txt in placeholder.value.data.items()], before="")
            
            text += f"\n🔑 Ключ: {placeholder.key}\n{texts}\n\n"
        
        return text
            
class AssortmentTextGen:
    @staticmethod
    def generate_viewing_entry_caption(product: Product, ctx: Context):
        price_text = f"<s>{product.base_price.to_text(ctx.customer.currency)}</s> {product.price.to_text(ctx.customer.currency)}" if product.discount else product.price.to_text(ctx.customer.currency)
        return f"{product.name.get(ctx)} — {price_text}\n\n{product.short_description.get(ctx)}" if product.short_description else f"{product.name.get(ctx)} — {price_text}"
    
    @staticmethod
    def generate_product_detailed_caption(product: Product, ctx: Context):
        price_text = f"<s>{product.base_price.to_text(ctx.customer.currency)}</s> {product.price.to_text(ctx.customer.currency)}" if product.discount else product.price.to_text(ctx.customer.currency)
        
        return f"{product.name.get(ctx)} — {price_text}\n\n{product.long_description.get(ctx)}"

    @staticmethod
    def generate_choice_text(option: ConfigurationOption, ctx: Context):
        chosen = option.get_chosen()

        description = chosen.description.get(ctx)

        if chosen.existing_presets: description = description.format(chosen=str(chosen.existing_presets_chosen))
        if chosen.is_custom_input and chosen.custom_input_text:
            description = f"<blockquote expandable>{html.quote(chosen.custom_input_text)}</blockquote>{description}"

        return f"{description}\n{option.text.get(ctx)}"

    @staticmethod
    def generate_switches_text(conf_switches: ConfigurationSwitches, ctx: Context):
        switches_and_groups = conf_switches.get_all()
        if not switches_and_groups:
            return (
                f"{conf_switches.description.get(ctx)}\n\n"
                + ctx.t.AssortmentTranslates.switches_enter
            )
        
        text = f"{conf_switches.description.get(ctx)}\n\n"
        for switch_or_group in switches_and_groups:
            if isinstance(switch_or_group, ConfigurationSwitch):
                text += f"{switch_or_group.name.get(ctx)} — {switch_or_group.price.to_text(ctx.customer.currency)} ( {'✅' if switch_or_group.enabled else '❌'} )\n"
                text += f"    {switch_or_group.description.get(ctx)}\n\n" if switch_or_group.description else "\n\n"
            elif isinstance(switch_or_group, ConfigurationSwitchesGroup):
                text += f"{switch_or_group.name.get(ctx)}:\n  — {switch_or_group.description.get(ctx)}\n"
                for switch in switch_or_group.get_all():
                    text += f"    {switch.name.get(ctx)} — {switch.price.to_text(ctx.customer.currency)} ( {'✅' if switch.enabled else '❌'} )\n"
                    text += f"        {switch.description.get(ctx)}\n" if switch.description else ""

        return f"{text}\n{ctx.t.AssortmentTranslates.switches_enter}"

    @staticmethod
    def generate_additionals_text(available: list[ProductAdditional], additionals: list[ProductAdditional], ctx: Context):
        def gen(additional: ProductAdditional):
            description = f"    {additional.description.get(ctx)}\n" if additional.description else ""
            
            return f"{additional.name.get(ctx)} — {additional.price.to_text(ctx.customer.currency)} ( {'✅' if additional in additionals else '❌'} )\n{description}"
        
        additionals_info = "\n".join([gen(additional) for additional in available])
        return f"\n{additionals_info}\n{ctx.t.AssortmentTranslates.switches_enter}"

    @staticmethod
    def generate_presets_text(ctx: Context):
        return f'{ctx.t.AssortmentTranslates.choose_the_preset}'

    @staticmethod
    def generate_custom_input_text(chosen: ConfigurationChoice, ctx: Context):
        content = chosen.description.get(ctx)
        content = (
            f"{content}\n\n<blockquote expandable>{html.quote(chosen.custom_input_text)}</blockquote>"
            if chosen.custom_input_text
            else content
        )
        content = f"{content}\n\n{ctx.t.AssortmentTranslates.enter_custom}"

        return content
    
    @staticmethod
    def generate_product_configurating_main(product: Product, ctx: Context):
        currency = ctx.customer.currency
        total_price = product.price + product.configuration.price

        section = gen_product_configurable_info_text(product.configuration, ctx)

        if product.configuration.requires_price_confirmation:
            price_text = f"\n\n{ctx.t.AssortmentTranslates.cannot_price}\n{ctx.t.AssortmentTranslates.approximate_price} {total_price.to_text(currency)}"
        else:
            price_text = f"\n\n{ctx.t.AssortmentTranslates.total} {total_price.to_text(currency)}"

        return f"{product.name.get(ctx)}\n\n{section}\n{price_text}"
    
    @staticmethod
    def gen_blocked_choice_path_text(choice_or_switch: ConfigurationChoice | ConfigurationSwitch, configuration: ProductConfiguration, ctx: Context):
        return " —> ".join(configuration.get_localized_names_by_path(choice_or_switch.get_blocking_path(configuration.options), ctx))

class DiscountedProductsGen:
    @staticmethod
    def generate_discounted_product_text(discounted_product: DiscountedProduct, ctx: Context):
        dprod_name = discounted_product.name.get(ctx)
        dprod_price = discounted_product.price.to_text(ctx.customer.currency)
        dprod_description = discounted_product.description.get(ctx)
        
        return f"{dprod_name} — {dprod_price}\n\n{dprod_description}" if discounted_product.description else f"{dprod_name} — {dprod_price}"
    
        

class ProfileTextGen:
    
    @staticmethod
    def referrals_menu_text(inviter: Inviter, ctx: Context):
        if inviter.inviter_type == InviterType.customer:
            menu_customer = ctx.t.ProfileTranslates.Referrals.menu_customer
            
            return menu_customer.format(invited_customers=inviter.invited_customers,
                                        people=ctx.t.UncategorizedTranslates.people(inviter.invited_customers),
                                        ordered_once=inviter.invited_customers_first_orders,
                                        bonus_balance=ctx.customer.bonus_wallet.to_text())
        elif inviter.inviter_type == InviterType.channel:
            menu_channel = ctx.t.ProfileTranslates.Referrals.menu_channel

            return menu_channel.format(invited_customers=inviter.invited_customers,
                                        people=ctx.t.UncategorizedTranslates.people(inviter.invited_customers),
                                        ordered_once=inviter.invited_customers_first_orders)
    
    @staticmethod
    async def referrals_invitation_link_view_text(inviter: Inviter, ctx: Context):
        link = await inviter.gen_link(ctx)
        
        return ctx.t.ProfileTranslates.Referrals.invitation_link_view.format(link=link)

    @staticmethod
    async def hidden_invitation_link(inviter: Inviter, ctx: Context):
        link = await inviter.gen_link(ctx)
        me = await ctx.message.bot.get_me()
        
        return f"<a href=\"{link}\">@{me.username}</a>"
        
    @staticmethod
    def delivery_menu_text(delivery_info: Optional[DeliveryInfo], ctx: Context):
        if not delivery_info:
            return ctx.t.ProfileTranslates.Delivery.menu_not_configured
        service = delivery_info.service
        
        requirements = service.selected_option.requirements
        
        requirements_info_text = "\n".join([f"  {requirement.name.get(ctx)}: <tg-spoiler>{html.quote(requirement.value.get())}</tg-spoiler>" for requirement in requirements])
        return ctx.t.ProfileTranslates.Delivery.menu.format(delivery_service=service.name.get(ctx), service_price=service.price.to_text(ctx.customer.currency), delivery_req_lists_name=service.selected_option.name.get(ctx), requirements=requirements_info_text)

class CartTextGen:
    @staticmethod
    def generate_cart_viewing_caption(entry: CartEntry, product: Optional[Product], configuration: Optional[ProductConfiguration], ctx: Context):
        is_product = entry.source_type == CartItemSource.product
        
        source_name = product.name.get(ctx) if is_product else entry.frozen_snapshot.name.get(ctx)
        
        configuration_price = product.price + entry.configuration.price if is_product else entry.frozen_snapshot.price
        configuration_price_text = configuration_price.to_text(ctx.customer.currency)
        total_price = (configuration_price * entry.quantity).to_text(ctx.customer.currency)
        
        price_text = f"{configuration_price_text} * {entry.quantity} = {total_price}" if entry.quantity != 1 else configuration_price_text
        
        return ctx.t.CartTranslates.cart_view_menu.format(name=source_name, price=price_text, configuration=gen_product_configurable_info_text(configuration, ctx) if is_product else entry.frozen_snapshot.description.get(ctx))

    @staticmethod
    async def generate_cart_price_confirmation_caption(order: Order, ctx: Context):
        return ctx.t.CartTranslates.cart_price_confirmation.format(price=order.price_details.products_price.to_text())
        

    @staticmethod
    async def generate_order_forming_caption(order: Order, ctx: Context):
        promocode: Optional[Promocode] = await ctx.services.db.promocodes.find_one_by_id(order.promocode_id) if order.promocode_id else None
        price_details = order.price_details
        payment_method = order.payment_method
            
        entries = await ctx.services.db.cart_entries.find_entries_by_order(order) if order.state == OrderStateKey.waiting_for_forming else await ctx.services.db.cart_entries.find_customer_cart_entries(ctx.customer)
        cart_entries_description = await asyncio.gather(*(form_entry_description(entry, ctx) for entry in entries))
        cart_entries_description = build_list(cart_entries_description, before="▫️")
        
        order_configuration_menu_text = ctx.t.CartTranslates.OrderConfiguration.order_configuration_menu
        if promocode:
            promocode_info = ctx.t.CartTranslates.OrderConfiguration.promocode_info.format(code=promocode.code, 
                                                                                           discount=order.price_details.promocode_discount.to_text(),
                                                                                           description=promocode.description.get(ctx))
        else:
            promocode_info = ctx.t.CartTranslates.OrderConfiguration.no_promocode_applied
            
        bonus_money_info = f"{price_details.bonuses_applied.to_text()}" if price_details.bonuses_applied else ctx.t.CartTranslates.OrderConfiguration.not_using_bonus_money
        
        payment_method_info = payment_method.name.get(ctx) if payment_method else ctx.t.CartTranslates.OrderConfiguration.no_payment_method_selected
        
        delivery_info = ctx.customer.delivery_info
        delivery_service = f"{delivery_info.service.name.get(ctx)} — {price_details.delivery_price.to_text()}"
        delivery_requirements_info = build_list([f"{requirement.name.get(ctx)} - <tg-spoiler>{requirement.value.get()}</tg-spoiler>" for requirement in delivery_info.service.selected_option.requirements],
                                                padding=2)
        
        total = price_details.total_price.to_text()
        
        return order_configuration_menu_text.format(
            cart_entries_description=cart_entries_description,
            promocode_info=promocode_info,
            bonus_money_info=bonus_money_info,
            payment_method_info=payment_method_info,
            delivery_service=delivery_service,
            delivery_requirements_info=delivery_requirements_info,
            total=total
        )
    
    @staticmethod
    def generate_payment_method_setting_caption(order: Order, ctx: Context):
        choose_payment_method = ctx.t.CartTranslates.OrderConfiguration.choose_payment_method
        methods_info = "\n\n".join(
            f"<b>{method.name.get(ctx)}</b>{' (✅)' if name == order.payment_method_key else ''}:\n    {method.description.get(ctx)}"
            for name, method in SUPPORTED_PAYMENT_METHODS.get_enabled(ctx.customer.currency).items()
        )
        return choose_payment_method.format(methods_info=methods_info)
    
    @staticmethod
    def generate_payment_confirmation_caption(order: Order, ctx: Context):
        payment_method = order.payment_method

        if payment_method.manual and payment_method:
            payment_confirmation_manual = ctx.t.CartTranslates.OrderConfiguration.payment_confirmation_manual
            return payment_confirmation_manual.format(payment_method_name=payment_method.name.get(ctx),
                                                      payment_method_details=payment_method.payment_details.get(ctx))
        else:
            return # TODO

class OrdersTextGen:
        
    @staticmethod
    async def generate_orders_menu_text(orders: Iterable[Order], ctx: Context):
        def gen_order_summary(order: Order):
            if order.state == OrderStateKey.waiting_for_price_confirmation:
                price_info = f">{order.price_details.products_price.to_text()}"
            else:
                price_info = order.price_details.total_price.to_text()
            
            return f"#{order.puid} — {order.state.get_localized_name(ctx.lang)}: {price_info}"

        
        orders_info = "\n".join(gen_order_summary(order) for order in orders)
        
        
        return ctx.t.OrdersTranslates.menu.format(orders_info=orders_info)
    
    @staticmethod
    async def generate_order_viewing_caption(order: Order, ctx: Context):
        order_viewing_menu = ctx.t.OrdersTranslates.order_viewing_menu
        
        entries = await ctx.services.db.cart_entries.find_entries_by_order(order)
        entries_description = await asyncio.gather(*(form_entry_description(entry, ctx) for entry in entries))
        entries_description = build_list(entries_description, before="▫️")
        
        delivery_info = order.delivery_info
        delivery_description = ""
        if delivery_info:
            delivery_description = f"{delivery_info.service.name.get(ctx)} — {order.price_details.delivery_price.to_text()}\n"
            delivery_description += build_list([f"{requirement.name.get(ctx)} - <tg-spoiler>{requirement.value.get()}</tg-spoiler>" for requirement in delivery_info.service.selected_option.requirements],
                                                    padding=2)
        
        if order.state == OrderStateKey.waiting_for_price_confirmation:
            price_info = ctx.t.OrdersTranslates.waiting_for_price_confirmation_info
        else:
            price_info = ctx.t.OrdersTranslates.total_price_info.format(total_price=order.price_details.total_price.to_text())
            
        promocode = await ctx.services.db.promocodes.find_one_by_id(order.promocode_id) if order.promocode_id else None
        promocode_info = ctx.t.CartTranslates.OrderConfiguration.promocode_info.format(code=promocode.code, 
                                                                                           discount=order.price_details.promocode_discount.to_text(),
                                                                                           description=promocode.description.get(ctx)) if promocode else None
        
        bonus_money_info = f"{order.price_details.bonuses_applied.to_text()}" if order.price_details.bonuses_applied else None
        
        return order_viewing_menu.format(order_puid=order.puid,
                                            order_forming_date=order.id.generation_time.strftime("%d.%m.%Y %H:%M UTC"),
                                            order_entries_description=entries_description,
                                            order_status=order.state.get_localized_name(ctx.lang),
                                            delivery_info=ctx.t.OrdersTranslates.delivery_info.format(info=delivery_description) if delivery_info else "",
                                            payment_method=ctx.t.OrdersTranslates.payment_method.format(info=order.payment_method.name.get(ctx)) if order.payment_method else "",
                                            promocode_info=ctx.t.OrdersTranslates.promocode_info.format(info=promocode_info) if promocode else "",
                                            bonus_money_info=ctx.t.OrdersTranslates.bonus_money_info.format(info=bonus_money_info) if bonus_money_info else "",
                                            products_price=order.price_details.products_price.to_text(),
                                            price_info=price_info
                                            )