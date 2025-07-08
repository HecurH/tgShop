from aiogram import html


from src.classes.db_models import *
from src.classes.translates import AssortmentTranslates, ProfileTranslates


def generate_viewing_assortment_entry_caption(product, customer: Customer, lang: str):
    return f"{product.name.data[lang]} — {product.base_price.data[customer.currency]} {customer.get_selected_currency_symbol()}\n\n{product.short_description.data[lang]}"

def generate_product_detailed_caption(product, customer: Customer, lang: str):
    return f"{product.name.data[lang]} — {product.base_price.data[customer.currency]} {customer.get_selected_currency_symbol()}\n\n{product.long_description.data[lang]}"

def generate_choice_text(option: ConfigurationOption, lang: str):
    chosen = option.choices[option.chosen-1]

    description = chosen.description.data[lang]

    if chosen.existing_presets: description = description.format(chosen=str(chosen.existing_presets_chosen))
    if chosen.is_custom_input and chosen.custom_input_text:
        description = f"<blockquote expandable>{html.quote(chosen.custom_input_text)}</blockquote>{description}"

    return f"{description}\n{option.text.data[lang]}"

def generate_switches_text(conf_switches: ConfigurationSwitches, customer: Customer, lang: str):
    switches = conf_switches.switches
    switches_info = "\n".join([f"{switch.name.data[lang]} — {switch.price.data[customer.currency]} {customer.get_selected_currency_symbol()} ( {"✅" if switch.enabled else "❌"} )" for switch in switches])
    return (
        f"{conf_switches.description.data[lang]}\n\n{switches_info}\n\n"
        + AssortmentTranslates.translate("switches_enter", lang)
    )

def generate_additionals_text(available: list[ProductAdditional], additionals: list[ProductAdditional], customer: Customer, lang: str):
    additionals_info = "\n".join([f"{additional.name.data[lang]} — {additional.price.data[customer.currency]} {customer.get_selected_currency_symbol()} ( {"✅" if additional in additionals else "❌"} )\n    {additional.short_description.data[lang]}\n" for additional in available])
    return f"\n{additionals_info}\n\n" + AssortmentTranslates.translate(
        "switches_enter", lang
    )

def generate_presets_text(lang: str):

    return f'{AssortmentTranslates.translate("choose_the_preset", lang)}'

def generate_custom_input_text(chosen: ConfigurationChoice, lang: str):

    content = chosen.description.data[lang]
    content = (
        f"{content}\n\n<blockquote expandable>{html.quote(chosen.custom_input_text)}</blockquote>"
        if chosen.custom_input_text
        else content
    )
    content = f"{content}\n\n{AssortmentTranslates.translate("enter_custom", lang)}"

    return content

def settings_menu_text(lang: str):
    return ProfileTranslates.Settings.translate("menu", lang)

def delivery_menu_text(delivery_info: DeliveryInfo, lang: str):
    if not delivery_info.service:
        return ProfileTranslates.Delivery.translate("menu_not_configured", lang)
    service = delivery_info.service
    
    requirements = service.selected_option.requirements
    
    requirements_info_text = "\n".join([f"{requirement.name[lang]}: <tg-spoiler>{requirement.value}</tg-spoiler>" for requirement in requirements])
    return ProfileTranslates.Delivery.translate("menu", lang).format(delivery_service=service.name[lang], requirements=requirements_info_text)

def generate_change_currency_text(customer: Customer, lang: str):
    current_currency_text = ProfileTranslates.translate("current_currency", lang).format(currency=customer.currency)
    return f"{current_currency_text}\n{ProfileTranslates.translate("available_currencies", lang)}"

def generate_change_currency_confirmation_text(iso: str, lang: str):
    return ProfileTranslates.translate("currency_change_warning", lang).format(iso=iso)

def generate_product_configurating_main(product: Product, lang: str, customer: Customer):
    options = product.configuration.options
    currency_sign = customer.get_selected_currency_symbol()
    selected_currency = customer.currency

    selected_options = ""
    total_price = product.base_price.data[selected_currency]
    cannot_determine_price = False

    for option in options:
        conf_choice = option.choices[option.chosen - 1]

        if isinstance(conf_choice, ConfigurationChoice):
            conf_choice: ConfigurationChoice
            label = conf_choice.label.data[lang]
            price = conf_choice.price.data[selected_currency]

            if conf_choice.custom_input_text:
                cannot_determine_price = True

            presets_info = f" ({conf_choice.existing_presets_chosen})" if conf_choice.existing_presets else ""
            custom_text = f" — \n<blockquote expandable>{html.quote(conf_choice.custom_input_text)}</blockquote>" if conf_choice.is_custom_input else ""

            if price > 0:
                price_info = f" +{price:.2f} {currency_sign}"
            elif price < 0:
                price_info = f" {price:.2f} {currency_sign}"
            else:
                price_info = ""

            total_price += price
            value = f"{label}{presets_info}{price_info}{custom_text}"
            selected_options += f"\n  {option.name.data[lang]}: {value}"
        for choice in option.choices:
            if isinstance(choice, ConfigurationSwitches):
                choice: ConfigurationSwitches

                label = choice.label.data[lang]
                enabled_switches = choice.get_enabled()
                if len(enabled_switches) == 0: break

                switches_text = ""

                for switch in enabled_switches:
                    name = switch.name.data[lang]
                    price = switch.price.data[selected_currency]

                    switches_text += f"\n      {name} — {'+' if price > 0 else ''}{price} {currency_sign}"


                total_price += choice.calculate_price(enabled_switches, selected_currency)

                selected_options += f"\n  {label}:{switches_text}"

    if len(product.configuration.additionals) > 0:
        selected_options += f"\n\n  {AssortmentTranslates.translate("additionals", lang)}"
        for additional in product.configuration.additionals:
            name = additional.name.data[lang]
            price = additional.price.data[selected_currency]

            total_price += price
            selected_options += f"\n      {name} — {'+' if price > 0 else ''}{price} {currency_sign}"

    section = f"{AssortmentTranslates.translate('currently_selected', lang)}\n{selected_options}"

    if cannot_determine_price:
        price_text = f"\n\n{AssortmentTranslates.translate('cannot_price', lang)}\n{AssortmentTranslates.translate('approximate_price', lang)} {total_price:.2f} {currency_sign}"
    else:
        price_text = f"\n\n{AssortmentTranslates.translate('total', lang)} {total_price:.2f} {currency_sign}"

    return f"{product.name.data[lang]}\n\n{section}\n{price_text}"
