from aiogram import types


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