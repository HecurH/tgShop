from aiogram import types
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from src.classes.db import DB
from src.classes.translates import ReplyButtonsTranslates, AssortmentTranslates, UncategorizedTranslates


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
        input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", lang))

