from aiogram.fsm.context import FSMContext

from aiogram import Router
from aiogram.filters import CommandObject, StateFilter, ChatMemberUpdatedFilter, MEMBER, KICKED
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated
from src.classes.db import *
from src.classes.middlewares import MongoDBMiddleware
from src.handlers.common import command_start_handler

router = Router(name="bottom")

# Если нет состояния
@router.message(StateFilter(None))
async def base_handler(message: Message, state: FSMContext, db, lang):
    await state.clear()
    #await message.reply(UncategorizedTranslates.oopsie[lang if lang != "?" else "ru"], reply_markup=ReplyKeyboardRemove())

    await command_start_handler(message, CommandObject(), state, db, lang)

@router.message()
async def real_base_handler(message: Message, state: FSMContext, db, lang):
    await message.delete()

@router.callback_query()
async def base_callback_handler(callback: CallbackQuery, state: FSMContext, db: DB, lang: str, middleware: MongoDBMiddleware) -> None:
    await callback.answer()

@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED))
async def user_blocked_bot(event: ChatMemberUpdated, state: FSMContext, db: DB):
    await state.clear()

    user = await db.customers.get_user_by_id(event.from_user.id)
    if user:
        user.kicked = True
        await db.update(user)


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def user_unblocked_bot(event: ChatMemberUpdated, state: FSMContext, db: DB):
    await state.clear()

    user = await db.customers.get_user_by_id(event.from_user.id)
    if user:
        user.kicked = False
        await db.update(user)