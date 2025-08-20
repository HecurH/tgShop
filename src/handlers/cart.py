from aiogram import Router
from schemas.db_models import CartEntry, Order, OrderPriceDetails
from core.helper_classes import Context
from core.states import Cart, CommonStates, Profile, call_state_handler
from ui.translates import *

router = Router(name="cart")

@router.message(CommonStates.MainMenu, lambda message: (message.text in ReplyButtonsTranslates.cart.values()) if message.text else False)
async def profile_entrance_handler(_, ctx: Context) -> None:
    await ctx.fsm.update_data(current=1)
    await call_state_handler(Cart.Menu, current=1, ctx=ctx)

@router.message(Cart.Menu)
async def cart_viewer_handler(_, ctx: Context):
    text = ctx.message.text
    
    if text == ctx.t.UncategorizedTranslates.back:
        await call_state_handler(CommonStates.MainMenu,
                                ctx)
        return
    
    amount = await ctx.db.cart_entries.count_customer_cart_entries(ctx.customer)
    current = await ctx.fsm.get_value("current") or 1
    
    if text == '❌':
        await call_state_handler(Cart.EntryRemoveConfirm, ctx)
        return
    elif text in ['⬅️', '➡️']:
        new_order = 1
        if text == '⬅️':
            new_order = amount if current == 1 else current - 1
        elif text == '➡️':
            new_order = 1 if current == amount else current + 1
        # if new_order > amount: new_order = 1
        
        await ctx.fsm.update_data(current=new_order)
        await call_state_handler(Cart.Menu,
                                ctx,
                                current=new_order)
    elif text in ['➖', '➕']:
        entry: CartEntry = await ctx.db.cart_entries.get_customer_cart_entry_by_id(ctx.customer, current-1)
        if text == '➖':
            entry.quantity = entry.quantity if entry.quantity == 1 else entry.quantity - 1
        elif text == '➕':
            entry.quantity = entry.quantity if entry.quantity == 99 else entry.quantity + 1
        await ctx.db.cart_entries.save(entry)

        await call_state_handler(Cart.Menu,
                                ctx,
                                current=current)
    elif text.rsplit(" ", 1)[0] == ReplyButtonsTranslates.Cart.translate("place", ctx.lang).format(price="").strip():
        if not ctx.customer.delivery_info:
            await ctx.fsm.update_data(back_to_cart_after_delivery=True)
            await call_state_handler(Profile.Delivery.Menu,
                                     ctx,
                                     send_before=(CartTranslates.translate("delivery_not_configured", ctx.lang), 1))
            return
        
        products_price = await ctx.db.cart_entries.calculate_customer_cart_price(ctx.customer)
        
        order = ctx.db.orders.new_order(ctx.customer, products_price)
        await ctx.fsm.update_data(order=order.model_dump())
        
        await call_state_handler(Cart.OrderConfigurationMenu,
                                 order=order,
                                 ctx=ctx)

    else:
        await call_state_handler(Cart.Menu,
                                ctx,
                                current=current)
        
@router.message(Cart.EntryRemoveConfirm)
async def entry_remove_confirm_handler(_, ctx: Context):
    current = await ctx.fsm.get_value("current")
    
    if not current:
        await call_state_handler(Cart.Menu,
                                 ctx,
                                 current=1,
                                 send_before="Can't find this item in cart.")
    
    if ctx.message.text == UncategorizedTranslates.translate("yes", ctx.lang):
        entry = await ctx.db.cart_entries.get_customer_cart_entry_by_id(ctx.customer, current-1)
        await ctx.db.cart_entries.delete(entry)
    
    current = max(1, current - 1)
    await ctx.fsm.update_data(current=current)
    await call_state_handler(Cart.Menu,
                                ctx,
                                current=current)

@router.message(Cart.OrderConfigurationMenu)
async def order_configuration_handler(_, ctx: Context):
    text = ctx.message.text
    if text == ctx.t.UncategorizedTranslates.back:
        await call_state_handler(CommonStates.MainMenu,
                                ctx)
        return