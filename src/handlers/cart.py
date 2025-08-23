from aiogram import Router
from configs.payments import SUPPORTED_PAYMENT_METHODS
from schemas.db_models import CartEntry, Order, OrderPriceDetails, Promocode
from core.helper_classes import Context
from core.states import Cart, CommonStates, Profile, call_state_handler
from schemas.enums import PromocodeCheckResult
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
            if entry.quantity == 1:
                await call_state_handler(Cart.EntryRemoveConfirm, ctx)
                return
            entry.quantity = entry.quantity - 1
        elif text == '➕':
            entry.quantity = entry.quantity if entry.quantity == 99 else entry.quantity + 1
        await ctx.db.cart_entries.save(entry)

        await call_state_handler(Cart.Menu,
                                ctx,
                                current=current)
    elif text.rsplit(" ", 1)[0] == ctx.t.ReplyButtonsTranslates.Cart.place.format(price="").strip():
        if not ctx.customer.delivery_info:
            await ctx.fsm.update_data(back_to_cart_after_delivery=True)
            await call_state_handler(Profile.Delivery.Menu,
                                     ctx,
                                     send_before=(ctx.t.CartTranslates.delivery_not_configured, 1))
            return
        
        products_price = await ctx.db.cart_entries.calculate_customer_cart_price(ctx.customer)
        
        order = ctx.db.orders.new_order(ctx.customer, products_price)
        await order.save_in_fsm(ctx, "order")
        
        await call_state_handler(Cart.OrderConfiguration.Menu,
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
    
    if ctx.message.text == ctx.t.UncategorizedTranslates.yes:
        entry = await ctx.db.cart_entries.get_customer_cart_entry_by_id(ctx.customer, current-1)
        await ctx.db.cart_entries.delete(entry)
    
    current = max(1, current - 1)
    await ctx.fsm.update_data(current=current)
    await call_state_handler(Cart.Menu,
                                ctx,
                                current=current)

@router.message(Cart.OrderConfiguration.Menu)
async def order_configuration_handler(_, ctx: Context):
    text = ctx.message.text
    if text == ctx.t.UncategorizedTranslates.back:
        await call_state_handler(Cart.Menu, ctx)
        return
    order: Order = await Order.from_fsm_context(ctx, "order")
    
    if text == ctx.t.ReplyButtonsTranslates.Cart.OrderConfiguration.use_promocode:
        await call_state_handler(Cart.OrderConfiguration.PromocodeSetting, ctx)
    elif text == ctx.t.ReplyButtonsTranslates.Cart.OrderConfiguration.use_bonus_money:
        pass
    elif text == ctx.t.ReplyButtonsTranslates.Cart.OrderConfiguration.change_payment_method:
        await call_state_handler(Cart.OrderConfiguration.PaymentMethodSetting, ctx, order=order)

@router.message(Cart.OrderConfiguration.PromocodeSetting)
async def order_configuration_promocode_handler(_, ctx: Context):
    text = ctx.message.text
    order: Order = await Order.from_fsm_context(ctx, "order")
    
    if text == ctx.t.UncategorizedTranslates.back:
        await call_state_handler(Cart.OrderConfiguration.Menu, ctx, order=order)
        return
    
    promocode: Promocode = await ctx.db.promocodes.get_by_code(text)
    if not promocode:
        await call_state_handler(Cart.OrderConfiguration.Menu, ctx, order=order, 
                                 send_before=(ctx.t.CartTranslates.OrderConfiguration.promocode_not_found, 1))
        return
    
    check_result: PromocodeCheckResult = await promocode.check_promocode(await ctx.db.orders.count_customer_orders(ctx.customer))
    
    if check_result != PromocodeCheckResult.ok:
        check_result_text = getattr(ctx.t.EnumTranslates.PromocodeCheckResult, str(check_result))
        check_result_text = ctx.t.CartTranslates.OrderConfiguration.promocode_check_failed.format(reason=check_result_text)
        
        await call_state_handler(Cart.OrderConfiguration.Menu, ctx, order=order, 
                                 send_before=(check_result_text, 1))
        return

    await order.set_promocode(promocode)
    await order.save_in_fsm(ctx, "order")
    
    await call_state_handler(Cart.OrderConfiguration.Menu, ctx, order=order, send_before=(ctx.t.CartTranslates.OrderConfiguration.promocode_applied, 1))

@router.message(Cart.OrderConfiguration.PaymentMethodSetting)
async def order_configuration_payment_method_handler(_, ctx: Context):
    text = ctx.message.text
    order: Order = await Order.from_fsm_context(ctx, "order")

    if text == ctx.t.UncategorizedTranslates.back:
        await call_state_handler(Cart.OrderConfiguration.Menu, ctx, order=order)
        return
    
    key, method = SUPPORTED_PAYMENT_METHODS.get_by_name(text.replace(" ✅", ""), ctx, only_enabled=True)
    if not method or order.payment_method_key == key:
        await call_state_handler(Cart.OrderConfiguration.PaymentMethodSetting, ctx, order=order)
        return
    
    order.payment_method_key = key
    await order.save_in_fsm(ctx, "order")
    
    text = ctx.t.CartTranslates.OrderConfiguration.payment_method_selected.format(name=method.name.get(ctx.lang))
    await call_state_handler(Cart.OrderConfiguration.Menu, ctx, order=order, send_before=(text, 1))