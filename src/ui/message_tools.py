import re
from typing import List, Optional, Literal
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InputMediaPhoto, ReplyKeyboardRemove, \
    InlineKeyboardMarkup, ReplyKeyboardMarkup, InputMediaVideo
    



async def clear_keyboard_effect(message: Message) -> None:
    """Костыльно удаляет клавиатуру."""
    msg = await message.answer("||BOO||", reply_markup=ReplyKeyboardRemove(), parse_mode="MarkdownV2")
    await msg.delete()

_tag_re = re.compile(
    r'<!--.*?-->|<\s*(/)?\s*([A-Za-z0-9][A-Za-z0-9\-\:]*)\b([^>]*)>',
    re.DOTALL
)

def _is_self_closing(full_tag: str) -> bool:
    return full_tag.rstrip().endswith("/>")

def _open_tags_stack(text: str):
    stack = []
    for m in _tag_re.finditer(text):
        full = m.group(0)
        if full.startswith("<!--"):
            continue
        closing = bool(m.group(1))
        tag_name = (m.group(2) or "").lower()
        if closing:
            # pop nearest matching
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == tag_name:
                    stack.pop(i)
                    break
        else:
            if not _is_self_closing(full):
                stack.append((tag_name, full))
    return stack

def _sanitize_unexpected_closing_tags(text: str) -> str:
    out = []
    pos = 0
    stack = []

    for m in _tag_re.finditer(text):
        start, end = m.span()
        out.append(text[pos:start])
        full = m.group(0)
        if full.startswith("<!--"):
            out.append(full)
        else:
            closing = bool(m.group(1))
            tag_name = (m.group(2) or "").lower()
            if closing:
                if stack and stack[-1] == tag_name:
                    stack.pop()
                    out.append(full)
                else:
                    # если нет соответствующего открывающего — экранируем
                    escaped = full.replace("<", "&lt;").replace(">", "&gt;")
                    out.append(escaped)
            else:
                if not _is_self_closing(full):
                    stack.append(tag_name)
                out.append(full)
        pos = end

    out.append(text[pos:])
    return "".join(out)

def split_message(text: str, limit: int) -> List[str]:
    if len(text) <= limit:
        return [text]

    parts = []
    buffer = text

    while len(buffer) > limit:
        cut = (
            buffer.rfind("\n\n", 0, limit)
            or buffer.rfind("\n", 0, limit)
            or buffer.rfind(" ", 0, limit)
        )
        if cut == -1 or cut < limit // 2:
            cut = limit

        # если попали внутрь тега — сдвинуть рез до ближайшего '>'
        last_lt = buffer.rfind("<", 0, cut)
        last_gt = buffer.rfind(">", 0, cut)
        if last_lt > last_gt:
            next_gt = buffer.find(">", cut)
            if next_gt != -1:
                cut = next_gt + 1

        head = buffer[:cut]
        tail = buffer[cut:]

        stack = _open_tags_stack(head)
        if stack:
            closing_suffix = "".join(f"</{name}>" for name, _ in reversed(stack))
            reopening_prefix = "".join(raw for _, raw in stack)
        else:
            closing_suffix = ""
            reopening_prefix = ""

        part_text = head.rstrip() + closing_suffix
        safe_part = _sanitize_unexpected_closing_tags(part_text)
        parts.append(safe_part)

        buffer = reopening_prefix + tail.lstrip()

    if buffer:
        parts.append(_sanitize_unexpected_closing_tags(buffer))

    return parts

def list_commands(router: Router) -> list[tuple[str, str]]:
    """Вернёт список (команда, описание) зарегистрированных команд в router."""
    result = []
    # router.routes или router.handlers / router.messages — в зависимости от версии
    for route in router.message.handlers:  
        # Проверяем, что это MessageRoute или что route содержит фильтр Command
        for flt in route.filters:  
            print(route)
            if isinstance(flt.callback, Command):
                # можем взять команды (string или список)
                doc = route.callback.__doc__ or ""
                result.append((", ".join(flt.callback.commands), doc.strip()))
    return result
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