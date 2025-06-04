from aiogram import html


from src.classes.db_models import *
from src.classes.translates import AssortmentTranslates, UncategorizedTranslates


def generate_viewing_assortment_entry_caption(product, currency, lang: str):
    content = f"{product.name.data[lang]} — {product.base_price.data[lang]} {currency}\n\n{product.short_description.data[lang]}"


    return content

def generate_product_detailed_caption(product, currency, lang: str):
    content = f"{product.name.data[lang]} — {product.base_price.data[lang]} {currency}\n\n{product.long_description.data[lang]}"


    return content

def generate_choice_text(option: ConfigurationOption, lang: str):
    chosen = option.choices[option.chosen-1]

    description = chosen.description.data[lang]

    if chosen.existing_presets: description = description.replace("CHOSEN", str(chosen.existing_presets_chosen))
    if chosen.is_custom_input and chosen.custom_input_text: description = f"<blockquote expandable>{html.quote(chosen.custom_input_text)}</blockquote>" + description

    content = f"{description}\n{option.text.data[lang]}"

    return content

def generate_switches_text(conf_switches: ConfigurationSwitches, lang: str):
    currency_sign = UncategorizedTranslates.translate("currency_sign", lang)
    switches = conf_switches.switches
    switches_info = "\n".join([f"{switch.name.data[lang]} — {switch.price.data[lang]} {currency_sign} ( {"✅" if switch.enabled else "❌"} )" for switch in switches])
    content = conf_switches.description.data[lang] + f"\n\n{switches_info}\n\n" + AssortmentTranslates.translate("switches_enter", lang)

    return content

def generate_additionals_text(available: list[ProductAdditional], additionals: list[ProductAdditional], lang: str):
    currency_sign = UncategorizedTranslates.translate("currency_sign", lang)

    additionals_info = "\n".join([f"{additional.name.data[lang]} — {additional.price.data[lang]} {currency_sign} ( {"✅" if additional in additionals else "❌"} )\n    {additional.short_description.data[lang]}\n" for additional in available])
    content = f"\n{additionals_info}\n\n" + AssortmentTranslates.translate("switches_enter", lang)

    return content

def generate_presets_text(chosen: ConfigurationChoice, lang: str):

    # content = chosen.description.data[lang]
    # content = content.replace("CHOSEN", str(chosen.existing_presets_chosen))
    content = f"{AssortmentTranslates.translate("choose_the_preset", lang)}"

    return content

def generate_cutom_input_text(chosen: ConfigurationChoice, lang: str):

    content = chosen.description.data[lang]
    content = content+f"\n\n<blockquote expandable>{html.quote(chosen.custom_input_text)}</blockquote>" if chosen.custom_input_text else content
    content = content + f"\n\n{AssortmentTranslates.translate("enter_custom", lang)}"

    return content


def generate_product_configurating_main(product: Product, lang: str):
    options = product.configuration.options
    currency_sign = UncategorizedTranslates.translate("currency_sign", lang)

    selected_options = ""
    total_price = product.base_price.data[lang]
    cannot_determine_price = False

    for option in options.values():
        conf_choice = option.choices[option.chosen - 1]

        if isinstance(conf_choice, ConfigurationChoice):
            conf_choice: ConfigurationChoice
            label = conf_choice.label.data[lang]
            price = conf_choice.price.data[lang]

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
                    price = switch.price.data[lang]

                    switches_text += f"\n      {name} — {'+' if price > 0 else ''}{price} {currency_sign}"


                total_price += choice.calculate_price(enabled_switches, lang)

                selected_options += f"\n  {label}:{switches_text}"

    if len(product.configuration.additionals) > 0:
        selected_options += f"\n\n  {AssortmentTranslates.translate("additionals", lang)}"
        for additional in product.configuration.additionals:
            name = additional.name.data[lang]
            price = additional.price.data[lang]

            total_price += price
            selected_options += f"\n      {name} — {'+' if price > 0 else ''}{price} {currency_sign}"

    section = f"{AssortmentTranslates.translate('currently_selected', lang)}\n{selected_options}"

    if cannot_determine_price:
        price_text = f"\n\n{AssortmentTranslates.translate('cannot_price', lang)}\n{AssortmentTranslates.translate('price_will_be_higher', lang)} {total_price:.2f} {currency_sign}"
    else:
        price_text = f"\n\n{AssortmentTranslates.translate('total', lang)} {total_price:.2f} {currency_sign}"

    return f"{product.name.data[lang]}\n\n{section}\n{price_text}"
