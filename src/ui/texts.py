from aiogram import html

from schemas.db_models import *
from ui.translates import AssortmentTranslates, CartTranslates, ProfileTranslates


def gen_product_configurable_info_text(configuration: ProductConfiguration, lang: str, customer: Customer):
    options = configuration.options
    currency = customer.currency
    selected_options = ""

    for option in options.values():
        conf_choice = option.get_chosen()

        if isinstance(conf_choice, ConfigurationChoice):
            label = conf_choice.label.get(lang)
            price = option.calculate_price()
            presets = f" ({conf_choice.existing_presets_chosen})" if conf_choice.existing_presets else ""
            custom = f" — \n<blockquote expandable>{html.quote(conf_choice.custom_input_text)}</blockquote>" if conf_choice.is_custom_input else ""
            price_val = price.get_amount(currency)
            if (len(option.get_switches()) > 1 or conf_choice.price.get_amount(currency) != 0) and price.get_amount(currency) != 0:
                sign = "+" if price.get_amount(currency) > 0 else ""
                price_info = f" {sign}{price.to_text(currency)}"
            else:
                price_info = ""
            value = f"{label}{presets}{price_info}{custom}"
            selected_options += f"\n▫️ {option.name.get(lang)}: {value}"
        for choice in option.choices.values():
            if isinstance(choice, ConfigurationSwitches):
                enabled_switches = choice.get_enabled()
                if not enabled_switches: 
                    break
                
                switches_text = ""
                for switch in enabled_switches:
                    name = switch.name.get(lang)
                    price = switch.price
                    price_val = price.get_amount(currency)
                    price_info = f" +{price.to_text(currency)}" if price_val > 0 else price.to_text(currency)

                    switches_text += f"\n      — {name}{price_info}"

                selected_options += switches_text

    if additionals := configuration.additionals:
        price = configuration.calculate_additionals_price()
        add_price = f" ({price.to_text(currency)})" if price.get_amount(currency) > 0 and len(additionals) > 1 else ""
        selected_options += f"\n\n➕ {AssortmentTranslates.translate('additionals', lang)}{add_price}:"
        for additional in additionals:
            name = additional.name.get(lang)
            price = additional.price
            price_val = price.get_amount(currency)
            price_info = f" +{price.to_text(currency)}" if price_val > 0 else price.to_text(currency)
            selected_options += f"\n    • {name}{price_info}"

    return f"{AssortmentTranslates.translate('currently_selected', lang)}\n{selected_options}"

class AssortmentTextGen:
    @staticmethod
    def generate_viewing_entry_caption(product, customer: Customer, lang: str):
        return f"{product.name.get(lang)} — {product.base_price.to_text(customer.currency)}\n\n{product.short_description.get(lang)}"
    
    @staticmethod
    def generate_product_detailed_caption(product, customer: Customer, lang: str):
        return f"{product.name.get(lang)} — {product.base_price.to_text(customer.currency)}\n\n{product.long_description.get(lang)}"

    @staticmethod
    def generate_choice_text(option: ConfigurationOption, lang: str):
        chosen = option.get_chosen()

        description = chosen.description.get(lang)

        if chosen.existing_presets: description = description.format(chosen=str(chosen.existing_presets_chosen))
        if chosen.is_custom_input and chosen.custom_input_text:
            description = f"<blockquote expandable>{html.quote(chosen.custom_input_text)}</blockquote>{description}"

        return f"{description}\n{option.text.get(lang)}"

    @staticmethod
    def generate_switches_text(conf_switches: ConfigurationSwitches, customer: Customer, lang: str):
        switches = conf_switches.switches
        switches_info = "\n".join([f"{switch.name.get(lang)} — {switch.price.to_text(customer.currency)} ( {'✅' if switch.enabled else '❌'} )" for switch in switches])
        return (
            f"{conf_switches.description.get(lang)}\n\n{switches_info}\n\n"
            + AssortmentTranslates.translate("switches_enter", lang)
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
    def generate_product_configurating_main(product: Product, lang: str, customer: Customer):
        currency = customer.currency
        total_price = product.base_price + product.configuration.price
        cannot_determine_price = False


        section = gen_product_configurable_info_text(product.configuration, lang, customer)

        if cannot_determine_price:
            price_text = f"\n\n{AssortmentTranslates.translate('cannot_price', lang)}\n{AssortmentTranslates.translate('approximate_price', lang)} {total_price.to_text(currency)}"
        else:
            price_text = f"\n\n{AssortmentTranslates.translate('total', lang)} {total_price.to_text(currency)}"

        return f"{product.name.get(lang)}\n\n{section}\n{price_text}"
    
    @staticmethod
    def gen_blocked_choice_path_text(choice: ConfigurationChoice, configuration: ProductConfiguration, lang):
        return " —> ".join(configuration.get_localized_names_by_path(choice.get_blocking_path(configuration.options), lang))

class ProfileTextGen:
    @staticmethod
    def settings_menu_text(lang: str):
        return ProfileTranslates.Settings.translate("menu", lang)
    
    @staticmethod
    def delivery_menu_text(delivery_info: DeliveryInfo, customer: Customer, lang: str):
        if not delivery_info.service:
            return ProfileTranslates.Delivery.translate("menu_not_configured", lang)
        service = delivery_info.service
        
        requirements = service.selected_option.requirements
        
        requirements_info_text = "\n".join([f"  {requirement.name.get(lang)}: <tg-spoiler>{requirement.value.get()}</tg-spoiler>" for requirement in requirements])
        return ProfileTranslates.Delivery.translate("menu", lang).format(delivery_service=service.name.get(lang), service_price=service.price.to_text(customer.currency), delivery_req_lists_name=service.selected_option.name.get(lang), requirements=requirements_info_text)

class CartTextGen:
    @staticmethod
    def generate_cart_viewing_caption(entry: CartEntry, product: Product, configuration: ProductConfiguration, customer, lang: str):
        
        configuration_price = product.base_price + entry.configuration.price
        configuration_price_text = configuration_price.to_text(customer.currency)
        total_price = (configuration_price * entry.quantity).to_text(customer.currency)
        
        price_text = f"{configuration_price_text} * {entry.quantity} = {total_price}" if entry.quantity != 1 else configuration_price_text
        
        return CartTranslates.translate("cart_view_menu", lang).format(name=product.name.get(lang), price=price_text, configuration=gen_product_configurable_info_text(configuration, lang, customer))
