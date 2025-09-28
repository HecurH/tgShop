from aiogram import Router
from configs.payments import SUPPORTED_PAYMENT_METHODS
from schemas.db_models import CartEntry, Order, OrderPriceDetails, Promocode
from core.helper_classes import Context
from core.states import CartStates, CommonStates, ProfileStates, call_state_handler
from schemas.enums import OrderStateKey, PromocodeCheckResult
from schemas.types import OrderState
from ui.translates import *

router = Router(name="cart")

@router.message(CommonStates.MainMenu, lambda message: (message.text in ReplyButtonsTranslates.cart.values()) if message.text else False)
async def profile_entrance_handler(_, ctx: Context) -> None:
    await ctx.fsm.update_data(current=1)
    await call_state_handler(CartStates.Menu, current=1, ctx=ctx)

@router.message(CartStates.Menu)
async def cart_viewer_handler(_, ctx: Context):
    text = ctx.message.text
    
    if text == ctx.t.UncategorizedTranslates.back:
        await call_state_handler(CommonStates.MainMenu,
                                ctx)
        return
    
    amount = await ctx.services.db.cart_entries.count_customer_cart_entries(ctx.customer)
    current = await ctx.fsm.get_value("current") or 1
    
    if text == '❌':
        await call_state_handler(CartStates.EntryRemoveConfirm, ctx)
        return
    elif text in ['⬅️', '➡️']:
        new_order = 1
        if text == '⬅️':
            new_order = amount if current == 1 else current - 1
        elif text == '➡️':
            new_order = 1 if current == amount else current + 1
        # if new_order > amount: new_order = 1
        
        await ctx.fsm.update_data(current=new_order)
        await call_state_handler(CartStates.Menu,
                                ctx,
                                current=new_order)
    elif text in ['➖', '➕']:
        entry: CartEntry = await ctx.services.db.cart_entries.find_customer_cart_entry_by_id(ctx.customer, current-1)
        if entry:
            if text == '➖':
                if entry.quantity == 1:
                    await call_state_handler(CartStates.EntryRemoveConfirm, ctx)
                    return
                entry.quantity = entry.quantity - 1
            elif text == '➕':
                entry.quantity = min(entry.quantity + 1, 99)
            await ctx.services.db.cart_entries.save(entry)

        await call_state_handler(CartStates.Menu,
                                ctx,
                                current=current)
    elif text.rsplit(" ", 1)[0] == ctx.t.ReplyButtonsTranslates.Cart.place.format(price="").strip() or text == ctx.t.ReplyButtonsTranslates.Cart.send_to_check:
        if not ctx.customer.delivery_info:
            await ctx.fsm.update_data(back_to_cart_after_delivery=True)
            await call_state_handler(ProfileStates.Delivery.Menu,
                                     ctx,
                                     send_before=(ctx.t.CartTranslates.delivery_not_configured, 1))
            return
        
        products_price = await ctx.services.db.cart_entries.calculate_customer_cart_price(ctx.customer)
        
        
        requires_price_confirmation = await ctx.services.db.cart_entries.check_price_confirmation_in_cart(ctx.customer)
        order = ctx.services.db.orders.new_order(ctx.customer, products_price, save_delivery_info=not requires_price_confirmation)
        await order.save_in_fsm(ctx, "order")
        
        if requires_price_confirmation:
            await call_state_handler(CartStates.CartPriceConfirmation, ctx, order=order)
            return
        
        await call_state_handler(CartStates.OrderConfiguration.Menu, ctx, order=order)

    else:
        await call_state_handler(CartStates.Menu,
                                ctx,
                                current=current)
        
@router.message(CartStates.EntryRemoveConfirm)
async def entry_remove_confirm_handler(_, ctx: Context):
    current = await ctx.fsm.get_value("current") or 1
    
    if not current:
        await call_state_handler(CartStates.Menu,
                                 ctx,
                                 current=1,
                                 send_before="Can't find this item in cart.")
        return
    
    if ctx.message.text == ctx.t.UncategorizedTranslates.yes:
        entry = await ctx.services.db.cart_entries.find_customer_cart_entry_by_id(ctx.customer, current-1)
        await ctx.services.db.cart_entries.delete(entry)
    
    current = max(1, current - 1)
    await ctx.fsm.update_data(current=current)
    await call_state_handler(CartStates.Menu,
                                ctx,
                                current=current)

@router.message(CartStates.CartPriceConfirmation)
async def cart_price_confirmation_handler(_, ctx: Context):
    text = ctx.message.text
    if text == ctx.t.UncategorizedTranslates.back or text != ctx.t.ReplyButtonsTranslates.Cart.send:
        await ctx.fsm.update_data(order=None)
        await call_state_handler(CartStates.Menu, ctx)
        return
    
    order: Order = await Order.from_fsm_context(ctx, "order")
    order.state.set_state(OrderStateKey.waiting_for_price_confirmation)
    
    await ctx.services.db.orders.save(order)
    await ctx.services.db.cart_entries.assign_cart_entries_to_order(ctx.customer, order)
    await ctx.services.notificators.AdminChatNotificator.send_price_confirmation(order, ctx)
    
    await ctx.fsm.update_data(order=None)
    await call_state_handler(CommonStates.MainMenu, ctx, send_before=(ctx.t.CartTranslates.price_confirmation_sent, 1))

@router.message(CartStates.OrderConfiguration.Menu)
async def order_configuration_handler(_, ctx: Context):
    back = ctx.t.UncategorizedTranslates.back
    use_promocode = ctx.t.ReplyButtonsTranslates.Cart.OrderConfiguration.use_promocode
    
    use_bonus_money = ctx.t.ReplyButtonsTranslates.Cart.OrderConfiguration.use_bonus_money
    no_bonus_money = ctx.t.CartTranslates.OrderConfiguration.no_bonus_money
    
    change_payment_method = ctx.t.ReplyButtonsTranslates.Cart.OrderConfiguration.change_payment_method
    choose_payment_method = ctx.t.ReplyButtonsTranslates.Cart.OrderConfiguration.choose_payment_method
    
    proceed_to_payment = ctx.t.ReplyButtonsTranslates.Cart.OrderConfiguration.proceed_to_payment
    
    text = ctx.message.text
    if text == back:
        await call_state_handler(CartStates.Menu, ctx)
        return
    order: Order = await Order.from_fsm_context(ctx, "order")
    
    if text == use_promocode:
        await call_state_handler(CartStates.OrderConfiguration.PromocodeSetting, ctx)
    elif text.strip("\u0336🔒>< ").replace("\u0336", "").replace("\u00a0", " ").strip().replace(" ✅", "") == use_bonus_money:
        if ctx.customer.bonus_wallet.amount > 0.0:
            await order.update_applied_bonuses(None if order.price_details.bonuses_applied else ctx.customer.bonus_wallet)
            
            await order.save_in_fsm(ctx, "order")
            await call_state_handler(CartStates.OrderConfiguration.Menu, ctx, order=order)
        else:
            await call_state_handler(CartStates.OrderConfiguration.Menu, ctx, order=order, 
                                     send_before=(no_bonus_money, 1))
    elif text in [change_payment_method, choose_payment_method]:
        await call_state_handler(CartStates.OrderConfiguration.PaymentMethodSetting, ctx, order=order)
    elif text == proceed_to_payment:
        payment_method = order.payment_method
        if not payment_method:
            await call_state_handler(CartStates.OrderConfiguration.Menu, ctx, order=order,
                                     send_before=(ctx.t.CartTranslates.OrderConfiguration.not_all_required_fields_filled, 1))
            return
        
        if not payment_method.manual: # TODO когда будет интернет-эквайринг
            return
        
        
        await call_state_handler(CartStates.OrderConfiguration.PaymentConfirmation, ctx, order=order)

@router.message(CartStates.OrderConfiguration.PromocodeSetting)
async def order_configuration_promocode_handler(_, ctx: Context):
    text = ctx.message.text
    order: Order = await Order.from_fsm_context(ctx, "order")
    
    if text == ctx.t.UncategorizedTranslates.back:
        await call_state_handler(CartStates.OrderConfiguration.Menu, ctx, order=order)
        return
    
    promocode: Promocode = await ctx.services.db.promocodes.find_by_code(text)
    if not promocode:
        await call_state_handler(CartStates.OrderConfiguration.Menu, ctx, order=order, 
                                 send_before=(ctx.t.CartTranslates.OrderConfiguration.promocode_not_found, 1))
        return
    
    check_result: PromocodeCheckResult = promocode.check_promocode(await ctx.services.db.orders.count_customer_orders(ctx.customer))
    
    if check_result != PromocodeCheckResult.ok:
        check_result_text = getattr(ctx.t.EnumTranslates.PromocodeCheckResult, str(check_result.name))
        check_result_text = ctx.t.CartTranslates.OrderConfiguration.promocode_check_failed.format(reason=check_result_text)
        
        await call_state_handler(CartStates.OrderConfiguration.Menu, ctx, order=order, 
                                 send_before=(check_result_text, 1))
        return

    await order.set_promocode(promocode)
    await order.save_in_fsm(ctx, "order")
    
    await call_state_handler(CartStates.OrderConfiguration.Menu, ctx, order=order, send_before=(ctx.t.CartTranslates.OrderConfiguration.promocode_applied, 1))

@router.message(CartStates.OrderConfiguration.PaymentMethodSetting)
async def order_configuration_payment_method_handler(_, ctx: Context):
    text = ctx.message.text
    order: Order = await Order.from_fsm_context(ctx, "order")

    if text == ctx.t.UncategorizedTranslates.back:
        await call_state_handler(CartStates.OrderConfiguration.Menu, ctx, order=order)
        return
    
    key, method = SUPPORTED_PAYMENT_METHODS.get_by_name(text.replace(" ✅", ""), ctx, only_enabled=True) or (None, None)
    if not method or order.payment_method_key == key:
        await call_state_handler(CartStates.OrderConfiguration.PaymentMethodSetting, ctx, order=order)
        return
    
    order.payment_method_key = key
    await order.save_in_fsm(ctx, "order")
    
    text = ctx.t.CartTranslates.OrderConfiguration.payment_method_selected.format(name=method.name.get(ctx))
    await call_state_handler(CartStates.OrderConfiguration.Menu, ctx, order=order, send_before=(text, 1))
    
@router.message(CartStates.OrderConfiguration.PaymentConfirmation)
async def order_configuration_payment_confirmation_handler(_, ctx: Context):
    text = ctx.message.text
    order: Order = await Order.from_fsm_context(ctx, "order")

    if text == ctx.t.UncategorizedTranslates.back:
        await call_state_handler(CartStates.OrderConfiguration.Menu, ctx, order=order)
        return
    
    if not order.payment_method.manual: # TODO когда будет интернет-эквайринг
        return

    if text == ctx.t.ReplyButtonsTranslates.Cart.OrderConfiguration.i_paid:
        entries_assigned = order.state == OrderStateKey.waiting_for_forming
        
        order.state.set_state(OrderStateKey.waiting_for_manual_payment_confirm)
        if order.promocode_id:
            promocode = await ctx.services.db.promocodes.find_one_by_id(order.promocode_id)
            if not promocode:
                order.promocode_id = None
            else:
                check_result = promocode.check_promocode()
                if check_result != PromocodeCheckResult.ok:
                    check_result_text = getattr(ctx.t.EnumTranslates.PromocodeCheckResult, str(check_result.name))
                    check_result_text = ctx.t.CartTranslates.OrderConfiguration.promocode_check_failed.format(reason=check_result_text)
                    
                    await call_state_handler(CartStates.OrderConfiguration.Menu, ctx, order=order, 
                                            send_before=(check_result_text, 1))
                    return
                    
                await ctx.services.db.promocodes.update_usage(order.promocode_id, 1)
        if order.price_details.bonuses_applied:
            await ctx.services.db.customers.remove_bonus_money(ctx.customer, order.price_details.bonuses_applied)
        
        await ctx.services.db.orders.save(order)
        
        if not entries_assigned: await ctx.services.db.cart_entries.assign_cart_entries_to_order(ctx.customer, order)
        
        await ctx.services.notificators.AdminChatNotificator.send_payment_confirmation(order, ctx)
        
        await ctx.fsm.update_data(order=None)
        
        await call_state_handler(CommonStates.MainMenu, ctx, send_before=(ctx.t.CartTranslates.OrderConfiguration.manual_payment_confirmation_sended, 1))
