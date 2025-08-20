from typing import List, Optional
from aiogram.types import Message, InputMediaPhoto, ReplyKeyboardRemove, \
    InlineKeyboardMarkup, ReplyKeyboardMarkup, InputMediaVideo



async def clear_keyboard_effect(message: Message) -> None:
    """Костыльно удаляет клавиатуру."""
    msg = await message.answer("||BOO||", reply_markup=ReplyKeyboardRemove(), parse_mode="MarkdownV2")
    await msg.delete()
    

async def send_media_response(
    message: Message,
    media_id: str,
    caption: str,
    keyboard: Optional[InlineKeyboardMarkup | ReplyKeyboardMarkup] = None,
    media_type: str = "photo"
) -> None:
    if media_type == "photo":
        await message.answer_photo(media_id, caption=caption, reply_markup=keyboard)
    elif media_type == "video":
        await message.answer_video(media_id, caption=caption, reply_markup=keyboard)
    else:
        await message.answer(caption, reply_markup=keyboard)

async def edit_media_message(
    message: Message,
    media_id: str,
    caption: str,
    reply_markup: Optional[InlineKeyboardMarkup | ReplyKeyboardMarkup] = None,
    media_type: str = "photo"
) -> None:
    """Редактирование медиа-сообщения"""
    # Получаем текущее содержимое сообщения
    current_caption = message.caption if hasattr(message, "caption") else None
    current_media_id = None
    if media_type == "photo" and getattr(message, "photo", None):
        current_media_id = message.photo[-1].file_id
    elif media_type == "video" and getattr(message, "video", None):
        current_media_id = message.video.file_id

    # Сравниваем содержимое
    if current_caption == caption and current_media_id == media_id and (
        (hasattr(message, "reply_markup") and message.reply_markup == reply_markup) or (not hasattr(message, "reply_markup") and not reply_markup)
    ):
        # Ничего не изменилось — не редактируем
        return

    media = InputMediaPhoto(media=media_id, caption=caption) if media_type == 'photo' else InputMediaVideo(media=media_id, caption=caption)
    await message.edit_media(media=media, reply_markup=reply_markup)

def strike(text:str): return "\u0336".join(f"{text} ".replace(" ", "\u00a0")) + "\u0336"

def build_list(entries: List[str], before: str = "—", padding: int = 1, default_padding_spaces: int = 2) -> str:
    """
    Создает форматированную строку-список с поддержкой вложенности.
    """
    spaces_amount = default_padding_spaces * padding
    indent = " " * spaces_amount
    formatted_entries = []
    for entry in entries:
        # Разбиваем строку по переводам строки и добавляем отступы к каждой части
        lines = entry.split('\n')
        first_line = f"{indent}{before} {lines[0]}"
        other_lines = [f"{indent}{line}" for line in lines[1:]]
        formatted_entries.append('\n'.join([first_line] + other_lines))
    return "\n".join(formatted_entries) if formatted_entries else ""