from aiogram import types
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

from src.classes.db import DB
from src.classes.db_models import ConfigurationOption
from src.classes.translates import ReplyButtonsTranslates, AssortmentTranslates, UncategorizedTranslates, \
    InlineButtonsTranslates


def lang_choose() -> types.InlineKeyboardMarkup:
    kb = [
        [
            types.InlineKeyboardButton(text="🇷🇺Русский", callback_data="ru"),
            types.InlineKeyboardButton(text="🇺🇸English", callback_data="en")
        ]
    ]
    return types.InlineKeyboardMarkup(
        inline_keyboard=kb
    )

def main_menu(lang: str) -> types.ReplyKeyboardMarkup:
    kb = [
        [
            types.KeyboardButton(text=ReplyButtonsTranslates.translate("assortment", lang)),
            types.KeyboardButton(text=ReplyButtonsTranslates.translate("orders", lang))
        ],
        [
            types.KeyboardButton(text=ReplyButtonsTranslates.translate("cart", lang)),
            types.KeyboardButton(text=ReplyButtonsTranslates.translate("about", lang))
        ]
    ]
    return types.ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", lang)
    )

async def assortment_menu(db: DB, lang: str) -> types.ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    for category in await db.categories.get_all():

        builder.add(types.KeyboardButton(text=AssortmentTranslates.translate(category.name, lang)))

    builder.add(types.KeyboardButton(text=UncategorizedTranslates.translate("back", lang)))
    builder.adjust(2)
    return builder.as_markup(
        resize_keyboard=True,
        #one_time_keyboard=True,
        input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", lang))


def gen_assortment_view_kb(current: int, amount: int, lang) -> types.InlineKeyboardMarkup:
    kb = [
        [
            types.InlineKeyboardButton(text=InlineButtonsTranslates.translate("details", lang),
                                       callback_data="details" if amount != 0 else "none")
        ],
        [
            types.InlineKeyboardButton(text="⬅️" if amount > 1 else "❌",
                                       callback_data="view_left" if amount > 1 else "none"),

            types.InlineKeyboardButton(text=f"{current}/{amount}",
                                       callback_data="none"),

            types.InlineKeyboardButton(text="➡️" if amount > 1 else "❌",
                                       callback_data="view_right" if amount > 1 else "none")
        ],
        [
            types.InlineKeyboardButton(text=UncategorizedTranslates.translate("back", lang), callback_data="back")
        ]
    ]
    return types.InlineKeyboardMarkup(
        inline_keyboard=kb
    )

def detailed_view(lang) -> types.InlineKeyboardMarkup:
    kb = [
        [
            types.InlineKeyboardButton(text=UncategorizedTranslates.translate("back", lang),
                                       callback_data="back"),

            types.InlineKeyboardButton(text=InlineButtonsTranslates.translate("add_to_cart", lang),
                                       callback_data="add_to_cart")
        ]
    ]
    return types.InlineKeyboardMarkup(
        inline_keyboard=kb
    )



def adding_to_cart_main(configurations: dict[str, ConfigurationOption], lang) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for option in configurations.values():
        builder.add(
            types.InlineKeyboardButton(
                text=option.name.data[lang],
                callback_data=option.name.data["en"]
            )
        )

    quantity = len(configurations.values())
    markup = types.InlineKeyboardMarkup(inline_keyboard=
                                        [
                                            [
                                                types.InlineKeyboardButton(
                                                    text=UncategorizedTranslates.translate("cancel", lang),
                                                    callback_data="cancel"),
                                                types.InlineKeyboardButton(
                                                    text=UncategorizedTranslates.translate("finish", lang),
                                                    callback_data="finish")
                                            ]
                                         ]
                                        )
    builder.adjust(2)
    builder.attach(InlineKeyboardBuilder.from_markup(markup))

    return builder.as_markup()



def inline_back(lang) -> types.InlineKeyboardMarkup:
    kb = [
        [
            types.InlineKeyboardButton(text=UncategorizedTranslates.translate("back", lang), callback_data="back")
        ]
    ]
    return types.InlineKeyboardMarkup(
        inline_keyboard=kb
    )

