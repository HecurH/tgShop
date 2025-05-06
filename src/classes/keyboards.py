from aiogram import types

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

def main_menu() -> types.ReplyKeyboardMarkup:
    kb = [
        [
            types.KeyboardButton(text="Ассортимент"),
            types.KeyboardButton(text="Заказы")
        ],
        [
            types.KeyboardButton(text="О нас")
        ]
    ]
    return types.ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        input_field_placeholder="Выберите пункт меню..."
    )