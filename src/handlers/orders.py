import asyncio
from aiogram import Router

from core.helper_classes import Context
from core.states import CartStates, CommonStates, OrderStates, call_state_handler
from schemas.db_models import Order, OrderPriceDetails
from core.types.enums import OrderStateKey
from ui.translates import ReplyButtonsTranslates


router = Router(name="orders")


@router.message(CommonStates.MainMenu, lambda message: (message.text in ReplyButtonsTranslates.orders.values()) if message.text else False)
async def profile_entrance_handler(_, ctx: Context) -> None:
    if await ctx.services.db.orders.count_customer_orders(ctx.customer) == 0:
        await call_state_handler(CommonStates.MainMenu, ctx, send_before=(ctx.t.OrdersTranslates.no_orders, 1))
        return
    
    await call_state_handler(OrderStates.Menu, ctx)
    
@router.message(OrderStates.Menu)
async def orders_menu_handler(_, ctx: Context) -> None:
    text = ctx.message.text
    if not text: return
    if text == ctx.t.UncategorizedTranslates.back:
        await call_state_handler(CommonStates.MainMenu, ctx)
        return
    
    if not text.startswith("#") and len(text) not in [5, 6]:
        await call_state_handler(OrderStates.Menu, ctx)
        return
    
    normalized_order_id = text[1:] if text.startswith("#") else text
    order = await ctx.services.db.orders.find_by_puid(normalized_order_id, ctx.customer)
    if not order:
        await call_state_handler(OrderStates.Menu, ctx)
        return
    
    await order.save_in_fsm(ctx, "order")
    await call_state_handler(OrderStates.OrderView, ctx, order=order)
    
@router.message(OrderStates.OrderView)
async def order_view_handler(_, ctx: Context) -> None:
    text = ctx.message.text
    if not text: return
    if text == ctx.t.UncategorizedTranslates.back:
        await ctx.fsm.update_data(order=None)
        await call_state_handler(OrderStates.Menu, ctx)
        return
    
    order: Order = await Order.from_fsm_context(ctx, "order")
    if text == ctx.t.ReplyButtonsTranslates.Orders.continue_forming and order.state == OrderStateKey.waiting_for_forming:
        products_price = await ctx.services.db.cart_entries.calculate_cart_entries_price_by_order(order)
        order.delivery_info = ctx.customer.privacy_data.delivery_info
        order.price_details = OrderPriceDetails.new(ctx.customer, products_price, ctx.customer.privacy_data.delivery_info)
        
        await order.save_in_fsm(ctx, "order")
        await call_state_handler(CartStates.OrderConfiguration.Menu, ctx, order=order)
        return
    
    if text in [ctx.t.ReplyButtonsTranslates.Orders.view_comment, ctx.t.ReplyButtonsTranslates.Orders.view_comments] and order.state.comment:
        for comment in order.state.get_comments():
            await ctx.message.bot.copy_message(chat_id=ctx.message.chat.id, from_chat_id=comment.chat_id, message_id=comment.message_id)
            await asyncio.sleep(0.2)
        
        await call_state_handler(OrderStates.OrderView, ctx, order=order)
        return
    
    
    attribute = ctx.t.ReplyButtonsTranslates.Orders.Infos.get_attribute(text, ctx.lang)
    
    await call_state_handler(OrderStates.OrderView, ctx, order=order, send_before=(getattr(ctx.t.OrdersTranslates.Infos, attribute), 2) if attribute else None)