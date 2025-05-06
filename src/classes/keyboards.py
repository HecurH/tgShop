from aiogram import types

from src.classes.translates import ReplyButtonsTranslates


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
            types.KeyboardButton(text=ReplyButtonsTranslates.assortment[lang]),
            types.KeyboardButton(text=ReplyButtonsTranslates.orders[lang])
        ],
        [
            types.KeyboardButton(text=ReplyButtonsTranslates.about[lang])
        ]
    ]
    return types.ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        input_field_placeholder=ReplyButtonsTranslates.choose_an_item[lang]
    )