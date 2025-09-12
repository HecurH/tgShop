import re
from typing import List, Optional, Literal
from aiogram.types import Message, InputMediaPhoto, ReplyKeyboardRemove, \
    InlineKeyboardMarkup, ReplyKeyboardMarkup, InputMediaVideo



async def clear_keyboard_effect(message: Message) -> None:
    """Костыльно удаляет клавиатуру."""
    msg = await message.answer("||BOO||", reply_markup=ReplyKeyboardRemove(), parse_mode="MarkdownV2")
    await msg.delete()

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr"
}

_tag_re = re.compile(r'<!--.*?-->|<\s*(/)?\s*([a-zA-Z0-9]+)([^>]*)>',
                     re.DOTALL)


def _open_tags_stack(text: str):
    stack = []
    for m in _tag_re.finditer(text):
        full = m.group(0)
        closing_slash = m.group(1)  # '/' если это закрывающий
        tag_name = (m.group(2) or "").lower()
        rest = m.group(3) or ""

        # пропускаем комментарии
        if full.startswith("<!--"):
            continue

        # определим, self-closing ли тег
        is_self_closing = False
        if full.rstrip().endswith("/>"):
            is_self_closing = True
        if tag_name in VOID_TAGS:
            is_self_closing = True

        if closing_slash:
            # закрывающий: pop ближайший открытый с таким именем
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == tag_name:
                    stack.pop(i)
                    break
            # иначе игнорируем (некорректный закрывающий)
        else:
            if not is_self_closing:
                # сохраняем raw открывающий тег (как есть, с атрибутами)
                stack.append((tag_name, full))
            # если self-closing — ничего не делаем
    return stack


def split_message(text: str, limit: int) -> List[str]:
    if len(text) <= limit:
        return [text]

    parts = []
    buffer = text

    while len(buffer) > limit:
        # ищем лучший разрез
        cut = (
            buffer.rfind("\n\n", 0, limit)
            or buffer.rfind("\n", 0, limit)
            or buffer.rfind(" ", 0, limit)
        )
        if cut == -1 or cut < limit // 2:  # не нашли нормального места
            cut = limit

        # если попали внутрь тега — сдвинуть рез до ближайшего '>' (чтобы не разрезать <...>)
        last_lt = buffer.rfind("<", 0, cut)
        last_gt = buffer.rfind(">", 0, cut)
        if last_lt > last_gt:
            # значит внутри тега
            next_gt = buffer.find(">", cut)
            if next_gt != -1:
                cut = next_gt + 1
            else:
                # нет закрывающей '>' — безопаснее отрезать до cut (попадание внутрь хз-что).
                # но затем мы попытаемся корректно закрыть/переоткрыть теги ниже.
                pass

        head = buffer[:cut]
        tail = buffer[cut:]

        # определить какие теги остаются открытыми в head
        stack = _open_tags_stack(head)  # список (name, raw_open_tag)

        # сформировать суффикс закрывающих тегов для текущей части
        if stack:
            closing_suffix = "".join(f"</{name}>" for name, _ in reversed(stack))
            # сформировать префикс (переоткрывающие теги) для следующей части
            # используем raw открывающие теги, чтобы сохранить атрибуты
            reopening_prefix = "".join(raw for _, raw in stack)
        else:
            closing_suffix = ""
            reopening_prefix = ""

        part_text = head.rstrip() + closing_suffix
        parts.append(part_text)

        # новый буфер — переоткрыть теги + оставшаяся часть
        buffer = (reopening_prefix + tail.lstrip())

    if buffer:
        parts.append(buffer)

    return parts

async def send_media_response(
    message: Message,
    media_id: str,
    caption: str,
    keyboard: Optional[InlineKeyboardMarkup | ReplyKeyboardMarkup] = None,
    media_type: Literal["photo", "video"] = "photo"
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