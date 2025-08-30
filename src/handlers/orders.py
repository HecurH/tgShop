from aiogram import Router

from core.helper_classes import Context
from core.states import CommonStates, Orders, call_state_handler
from schemas.db_models import Order
from ui.translates import OrdersTranslates, ReplyButtonsTranslates


router = Router(name="orders")


@router.message(CommonStates.MainMenu, lambda message: (message.text in ReplyButtonsTranslates.orders.values()) if message.text else False)
async def profile_entrance_handler(_, ctx: Context) -> None:
    await call_state_handler(Orders.Menu, ctx)
    
@router.message(Orders.Menu)
async def orders_menu_handler(_, ctx: Context) -> None:
    text = ctx.message.text
    if text == ctx.t.UncategorizedTranslates.back:
        await call_state_handler(CommonStates.MainMenu, ctx)
        return
    
    if not text.startswith("#") and len(text) not in [5, 6]:
        await call_state_handler(Orders.Menu, ctx)
        return
    
    normalized_order_id = text[1:] if text.startswith("#") else text
    order = await ctx.db.orders.get_by_puid(normalized_order_id, ctx.customer)
    if not order:
        await call_state_handler(Orders.Menu, ctx)
        return
    
    await order.save_in_fsm(ctx, "order")
    await call_state_handler(Orders.OrderView, ctx, order=order)
    
@router.message(Orders.OrderView)
async def order_view_handler(_, ctx: Context) -> None:
    text = ctx.message.text
    if text == ctx.t.UncategorizedTranslates.back:
        await ctx.fsm.update_data(order=None)
        await call_state_handler(Orders.Menu, ctx)
        return
    
    order = await Order.from_fsm_context(ctx, "order")
    attribute = ReplyButtonsTranslates.Orders.Infos.get_attribute(text, ctx.lang)
    
    await call_state_handler(Orders.OrderInfo, ctx, order=order, send_before=(getattr(OrdersTranslates.Infos, attribute), 2) if attribute else None)