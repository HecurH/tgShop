from aiogram import Router
from aiogram.types import Message, CallbackQuery

from ui.texts import AssortmentTextGen
from core.helper_classes import Context
from schemas.db_models import *

from core.states import DiscountedStates, CommonStates, call_state_handler
from ui.translates import ReplyButtonsTranslates, UncategorizedTranslates

router = Router(name="discounted_products")


@router.message(CommonStates.MainMenu, lambda message: (message.text in ReplyButtonsTranslates.discounted_products.values()) if message.text else False)
async def discounted_products_command_handler(_, ctx: Context) -> None:
    await ctx.fsm.update_data(current=1)
    
    await call_state_handler(DiscountedStates.ViewingProducts, ctx,
                             current=1)
    
@router.message(DiscountedStates.ViewingProducts)
async def viewing_discounted_products_handler(_, ctx: Context) -> None:
    text = ctx.message.text
    if not text: return
    
    if text == ctx.t.UncategorizedTranslates.back:
        await ctx.fsm.update_data(current=None)
        await call_state_handler(CommonStates.MainMenu, ctx)
        return
    
    current = await ctx.fsm.get_value("current") or 1
    
    amount = await ctx.services.db.discounted_products.count()
    
    if text in ["⬅️", "➡️"]:
        if text == '⬅️':
            new_order = amount if current == 1 else current - 1
        elif text == '➡️':
            new_order = 1 if current == amount else current + 1
            
        await ctx.fsm.update_data(current=new_order)
        await call_state_handler(DiscountedStates.ViewingProducts,
                                ctx,
                                current=new_order)
    elif text == ctx.t.ReplyButtonsTranslates.DiscountedProducts.add_to_cart:
        if amount == 0: 
            await ctx.message.delete()
            await call_state_handler(DiscountedStates.ViewingProducts,
                                ctx,
                                current=current)
            return
        
        discounted_product = await ctx.services.db.discounted_products.find_by_index(current-1)
        if await ctx.services.db.cart_entries.check_product_in_cart(discounted_product, ctx.customer):
            await call_state_handler(DiscountedStates.ViewingProducts,
                                ctx,
                                current=current,
                                send_before=(ctx.t.DiscountedProductsTranslates.already_in_cart, 1))
            return
        
        if await ctx.services.db.cart_entries.check_product_in_orders(discounted_product, ctx.customer):
            await call_state_handler(DiscountedStates.ViewingProducts,
                                ctx,
                                current=current,
                                send_before=(ctx.t.DiscountedProductsTranslates.already_ordered, 1))
            return
        
        await ctx.services.db.cart_entries.add_to_cart(discounted_product, ctx.customer)
        
        await ctx.fsm.update_data(current=None)
        await call_state_handler(CommonStates.MainMenu,
                                ctx,
                                send_before=(ctx.t.DiscountedProductsTranslates.added_to_cart, 1))
        
        
    else:
        await call_state_handler(DiscountedStates.ViewingProducts,
                                ctx,
                                current=current)