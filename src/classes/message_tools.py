from typing import Optional
from aiogram.types import PreCheckoutQuery, Message, LabeledPrice, CallbackQuery, InputMediaPhoto, ReplyKeyboardRemove, \
    InlineKeyboardMarkup, ReplyKeyboardMarkup, InputMediaVideo



async def clear_keyboard_effect(message: Message) -> None:
    """Костыльно удаляет клавиатуру."""
    msg = await message.answer("||BOO||", reply_markup=ReplyKeyboardRemove(), parse_mode="MarkdownV2")
    await msg.delete()
    

async def send_media_response(
    message: Message,
    media_id: Optional[str],
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
    media = InputMediaPhoto(media=media_id, caption=caption) if media_type == 'photo' else InputMediaVideo(media=media_id, caption=caption)
    await message.edit_media(media=media, reply_markup=reply_markup)
