import asyncio
from aiogram import html

from core.helper_classes import Context
from schemas.db_models import *
from schemas.payment_models import PaymentMethod
from ui.message_tools import build_list
from ui.translates import AssortmentTranslates, CartTranslates, ProfileTranslates, UncategorizedTranslates


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
        
        label = conf_choice.label.get(ctx.lang)
        
        presets = f" ({conf_choice.existing_presets_chosen})" if conf_choice.existing_presets and conf_choice.existing_presets_chosen else ""
        
        price_info = f" {gen_price_info(conf_choice.price)}" if conf_choice.price.get_amount(currency) != 0 else ""
        # if len(option.get_switches()) > 1 or price.get_amount(currency) != 0:
        #     price_info = f" {gen_price_info(price)}"
            
        custom = f" — \n<blockquote expandable>{html.quote(conf_choice.custom_input_text)}</blockquote>" if conf_choice.is_custom_input and conf_choice.custom_input_text else ""
        
        value = f"{label}{presets}{price_info}{custom}"
        selected_options = f"{option.name.get(ctx.lang)}: {value}"
        
        for choice in option.choices.values():
            if not isinstance(choice, ConfigurationSwitches):
                continue
            
            enabled_switches = choice.get_enabled()
            if not enabled_switches: 
                continue
            
            def switch_text(switch):
                name = switch.name.get(ctx.lang)
                return f"{name} {gen_price_info(switch.price)}"
            
            switches_text = "\n"
            switches_text += build_list([switch_text(switch) for switch in enabled_switches], padding=2)
            selected_options += switches_text
        return selected_options
    
    selected_options = build_list([generate_option_description(option) for option in options.values()], '▫️', 0)

    if additionals := configuration.additionals:
        price = configuration.calculate_additionals_price()
        add_price = f" ({price.to_text(currency)})" if price.get_amount(currency) > 0 and len(additionals) > 1 else ""
        selected_options += f"\n\n➕ {AssortmentTranslates.translate('additionals', ctx.lang)}{add_price}:\n"
        
        def gen_additional_text(additional):
            name = additional.name.get(ctx.lang)
            price = additional.price
            price_text = price.to_text(currency)
            price_info = f"+{price_text}" if price.get_amount(currency) > 0 else price.to_text(currency)
            return f"{name} {price_info}"
        
        selected_options += build_list([gen_additional_text(additional) for additional in additionals], '•', 2)

    return f"{AssortmentTranslates.translate('currently_selected', ctx.lang)}\n{selected_options}"

class AssortmentTextGen:
    @staticmethod
    def generate_viewing_entry_caption(product: Product, ctx: Context):
        return f"{product.name.get(ctx.lang)} — {product.price.to_text(ctx.customer.currency)}\n\n{product.short_description.get(ctx.lang)}"
    
    @staticmethod
    def generate_product_detailed_caption(product: Product, ctx: Context):
        return f"{product.name.get(ctx.lang)} — {product.price.to_text(ctx.customer.currency)}\n\n{product.long_description.get(ctx.lang)}"

    @staticmethod
    def generate_choice_text(option: ConfigurationOption, lang: str):
        chosen = option.get_chosen()

        description = chosen.description.get(lang)

        if chosen.existing_presets: description = description.format(chosen=str(chosen.existing_presets_chosen))
        if chosen.is_custom_input and chosen.custom_input_text:
            description = f"<blockquote expandable>{html.quote(chosen.custom_input_text)}</blockquote>{description}"

        return f"{description}\n{option.text.get(lang)}"

    @staticmethod
    def generate_switches_text(conf_switches: ConfigurationSwitches, ctx: Context):
        switches = conf_switches.switches
        if not switches:
            return (
                f"{conf_switches.description.get(ctx.lang)}\n\n"
                + AssortmentTranslates.translate("switches_enter", ctx.lang)
            )
        switches_info = "\n".join([f"{switch.name.get(ctx.lang)} — {switch.price.to_text(ctx.customer.currency)} ( {'✅' if switch.enabled else '❌'} )" for switch in switches])
        return (
            f"{conf_switches.description.get(ctx.lang)}\n\n{switches_info}\n\n"
            + AssortmentTranslates.translate("switches_enter", ctx.lang)
        )
        
    @staticmethod
    def generate_additionals_text(available: list[ProductAdditional], additionals: list[ProductAdditional], customer: Customer, lang: str):
        additionals_info = "\n".join([f"{additional.name.get(lang)} — {additional.price.to_text(customer.currency)} ( {'✅' if additional in additionals else '❌'} )\n    {additional.short_description.get(lang)}\n" for additional in available])
        return f"\n{additionals_info}\n\n" + AssortmentTranslates.translate(
            "switches_enter", lang
        )

    @staticmethod
    def generate_presets_text(lang: str):
        return f'{AssortmentTranslates.translate("choose_the_preset", lang)}'

    @staticmethod
    def generate_custom_input_text(chosen: ConfigurationChoice, lang: str):
        content = chosen.description.get(lang)
        content = (
            f"{content}\n\n<blockquote expandable>{html.quote(chosen.custom_input_text)}</blockquote>"
            if chosen.custom_input_text
            else content
        )
        content = f"{content}\n\n{AssortmentTranslates.translate('enter_custom', lang)}"

        return content
    
    @staticmethod
    def generate_product_configurating_main(product: Product, ctx: Context):
        currency = ctx.customer.currency
        total_price = product.price + product.configuration.price

        section = gen_product_configurable_info_text(product.configuration, ctx)

        if product.configuration.can_determine_price:
            price_text = f"\n\n{AssortmentTranslates.translate('cannot_price', ctx.lang)}\n{AssortmentTranslates.translate('approximate_price', ctx.lang)} {total_price.to_text(currency)}"
        else:
            price_text = f"\n\n{AssortmentTranslates.translate('total', ctx.lang)} {total_price.to_text(currency)}"

        return f"{product.name.get(ctx.lang)}\n\n{section}\n{price_text}"
    
    @staticmethod
    def gen_blocked_choice_path_text(choice: ConfigurationChoice, configuration: ProductConfiguration, lang):
        return " —> ".join(configuration.get_localized_names_by_path(choice.get_blocking_path(configuration.options), lang))

class ProfileTextGen:
    @staticmethod
    def settings_menu_text(lang: str):
        return ProfileTranslates.Settings.translate("menu", lang)
    
    @staticmethod
    def delivery_menu_text(delivery_info: Optional[DeliveryInfo], ctx: Context):
        if not delivery_info:
            return ProfileTranslates.Delivery.translate("menu_not_configured", ctx.lang)
        service = delivery_info.service
        
        requirements = service.selected_option.requirements
        
        requirements_info_text = "\n".join([f"  {requirement.name.get(ctx.lang)}: <tg-spoiler>{html.escape(requirement.value.get())}</tg-spoiler>" for requirement in requirements])
        return ProfileTranslates.Delivery.translate("menu", ctx.lang).format(delivery_service=service.name.get(ctx.lang), service_price=service.price.to_text(ctx.customer.currency), delivery_req_lists_name=service.selected_option.name.get(ctx.lang), requirements=requirements_info_text)

class CartTextGen:
    @staticmethod
    def generate_cart_viewing_caption(entry: CartEntry, product: Product, configuration: ProductConfiguration, ctx: Context):
        
        configuration_price = product.price + entry.configuration.price
        configuration_price_text = configuration_price.to_text(ctx.customer.currency)
        total_price = (configuration_price * entry.quantity).to_text(ctx.customer.currency)
        
        price_text = f"{configuration_price_text} * {entry.quantity} = {total_price}" if entry.quantity != 1 else configuration_price_text
        
        return CartTranslates.translate("cart_view_menu", ctx.lang).format(name=product.name.get(ctx.lang), price=price_text, configuration=gen_product_configurable_info_text(configuration, ctx))

    @staticmethod
    async def generate_order_forming_caption(order: Order, ctx: Context):
        promocode = order.promocode
        price_details = order.price_details
        payment_method = order.payment_method
        
        async def form_entry_desc(entry):
            product = await ctx.db.products.find_one_by_id(entry.product_id)
            quantity_text = f" {entry.quantity} {UncategorizedTranslates.translate('unit', ctx.lang, count=entry.quantity)}" if entry.quantity > 1 else ""
            price = product.price + entry.configuration.price
            price_text = price.to_text(ctx.customer.currency)
            price_text = f"{price_text} * {entry.quantity} = {(price*entry.quantity).to_text(ctx.customer.currency)}" if entry.quantity != 1 else price_text
            
            return f"{product.name.get(ctx.lang)}{quantity_text} — {price_text}"
            
        entries = await ctx.db.cart_entries.get_customer_cart_entries(ctx.customer)
        cart_entries_description = await asyncio.gather(*(form_entry_desc(entry) for entry in entries))
        cart_entries_description = build_list(cart_entries_description, before="▫️")
        
        order_configuration_menu_text = CartTranslates.OrderConfiguration.translate("order_configuration_menu", ctx.lang)
        promocode_info = f"{promocode.code} — {promocode.description.get(ctx.lang)}" if promocode else CartTranslates.OrderConfiguration.translate("no_promocode_applied", ctx.lang)
        bonus_money_info = f"{price_details.bonuses_applied.to_text()}" if price_details.bonuses_applied else CartTranslates.OrderConfiguration.translate("not_using_bonus_money", ctx.lang)
        
        payment_method_info = payment_method.name.get(ctx.lang) if payment_method else CartTranslates.OrderConfiguration.translate("no_payment_method_selected", ctx.lang)
        
        delivery_info = ctx.customer.delivery_info
        delivery_service = f"{delivery_info.service.name.get(ctx.lang)} — {price_details.delivery_price.to_text()}"
        delivery_requirements_info = build_list([f"{requirement.name.get(ctx.lang)} - <tg-spoiler>{requirement.value.get()}</tg-spoiler>" for requirement in delivery_info.service.selected_option.requirements],
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
        