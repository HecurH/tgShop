from aiogram import Router

from core.helper_classes import Context
from core.states import CommonStates, Orders, call_state_handler
from ui.translates import ReplyButtonsTranslates


router = Router(name="orders")


@router.message(CommonStates.MainMenu, lambda message: (message.text in ReplyButtonsTranslates.orders.values()) if message.text else False)
async def profile_entrance_handler(_, ctx: Context) -> None:
    await call_state_handler(Orders.Menu, ctx)