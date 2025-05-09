from aiogram.utils.formatting import Text, as_marked_section, as_key_value, Bold

from src.classes.db_models import ConfigurationOption, Product
from src.classes.translates import AssortmentTranslates


def generate_viewing_assortment_entry_caption(product, currency, lang):
    content = f"{product.name.data[lang]} - {product.base_price.data[lang]} {currency}\n\n{product.short_description.data[lang]}"


    return content

def generate_product_detailed_caption(product, currency, lang):
    content = f"{product.name.data[lang]} - {product.base_price.data[lang]} {currency}\n\n{product.long_description.data[lang]}"


    return content

def generate_product_configurating_main(product: Product, currency_sign, lang):
    configurations = product.configurations

    selected_options = []
    price = product.base_price.data[lang]
    for option in configurations.values():
        choice = option.choices[option.chosen - 1]
        label = choice.label.data[lang]
        price_adjustment = choice.price_adjustment.data[lang]

        # Добавляем информацию о пресетах, если они есть
        presets_info = f" ({choice.existing_presets_chosen})" if choice.existing_presets else ""

        # Форматируем ценовую корректировку, если она отличается от 0
        if price_adjustment > 0:
            price_info = f" +{price_adjustment:.2f} {currency_sign}"
        elif price_adjustment < 0:
            price_info = f" {price_adjustment:.2f} {currency_sign}"
        else:
            price_info = ""
        price += price_adjustment

        value = f"{label}{presets_info}{price_info}"

        selected_options.append(
            as_key_value(option.name.data[lang], value)
        )

    section = as_marked_section(
        AssortmentTranslates.translate("currently_selected", lang),
        *selected_options,
        marker="  "
    )
    price_text = Text(
        AssortmentTranslates.translate("total", lang), Bold(f"{price:.2f}"), Bold(currency_sign)
    )

    return Text(section, price_text).as_html()