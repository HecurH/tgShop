from aiogram import Dispatcher, Router
from aiogram.filters import StateFilter, ChatMemberUpdatedFilter, MEMBER, KICKED
from core.helper_classes import Context
from core.services.db import *
from core.states import call_state_handler, CommonStates

router = Router(name="bottom")

# Если нет состояния
@router.message(StateFilter(None))
async def base_handler(_, ctx: Context):
    await ctx.fsm.clear()
    await call_state_handler(CommonStates.MainMenu)

@router.message()
async def real_base_handler(_, ctx: Context):
    await ctx.message.delete()

@router.callback_query()
async def base_callback_handler(_, ctx: Context) -> None:
    await ctx.event.answer()

@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED))
async def user_blocked_bot(_, ctx: Context):
    if ctx.customer:
        ctx.customer.kicked = True
        await ctx.services.db.update(ctx.customer)

@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def user_unblocked_bot(_, ctx: Context):
    if ctx.customer:
        ctx.customer.kicked = False
        await ctx.services.db.update(ctx.customer)

@router.startup()
async def on_startup(dispatcher: Dispatcher):
    await dispatcher.workflow_data.get("context_middleware").start(dispatcher.workflow_data.get("bot"))

@router.shutdown()
async def on_shutdown(dispatcher: Dispatcher): await dispatcher.workflow_data.get("context_middleware").stop()