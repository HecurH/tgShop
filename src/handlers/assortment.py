from aiogram import Router
from aiogram.types import Message, CallbackQuery

from ui.texts import AssortmentTextGen
from core.helper_classes import Context
from schemas.db_models import *

from core.states import AssortmentStates, CommonStates, call_state_handler
from ui.translates import ReplyButtonsTranslates, UncategorizedTranslates

router = Router(name="assortment")

@router.message(CommonStates.MainMenu, lambda message: (message.text in ReplyButtonsTranslates.assortment.values()) if message.text else False)
async def assortment_command_handler(_, ctx: Context) -> None:
    await call_state_handler(AssortmentStates.Menu, ctx)

@router.message(AssortmentStates.Menu)
async def assortment_category_handler(_, ctx: Context) -> None:
    if ctx.message.text in UncategorizedTranslates.back.values():
        await call_state_handler(CommonStates.MainMenu,
                                 ctx)
        return

    category = next(
        (category.name for category in await ctx.services.db.categories.get_all()
         if category.localized_name.get(ctx) == ctx.message.text),
        None  # значение по умолчанию, если ничего не найдено
    )

    if not category:
        await call_state_handler(AssortmentStates.Menu, ctx)
        return

    await ctx.fsm.update_data(category=category, current=1)
    await call_state_handler(AssortmentStates.ViewingAssortment,
                             ctx,
                             category=category,
                             current=1)

@router.message(AssortmentStates.ViewingAssortment)
async def assortment_viewing_handler(_, ctx: Context) -> None:
    text = ctx.message.text
    if not text: return
    
    if text == ctx.t.UncategorizedTranslates.back:
        await call_state_handler(AssortmentStates.Menu,
                                ctx)
        return
    
    current = await ctx.fsm.get_value("current") or 1
    category = await ctx.fsm.get_value("category")
    amount = await ctx.services.db.products.count_in_category(category)
    
    if text in ["⬅️", "➡️"]:
        if text == '⬅️':
            new_order = amount if current == 1 else current - 1
        elif text == '➡️':
            new_order = 1 if current == amount else current + 1
            
        await ctx.fsm.update_data(current=new_order, category=category)
        await call_state_handler(AssortmentStates.ViewingAssortment,
                                ctx,
                                category=category,
                                current=new_order)
    elif text == ctx.t.ReplyButtonsTranslates.Assortment.details:
        if amount == 0: 
            await ctx.message.delete()
            return
        
        await ctx.fsm.update_data(product=None)
        
        product: Product = await ctx.services.db.products.find_by_category_and_index(category, current-1)
        await call_state_handler(AssortmentStates.ViewingProductDetails,
                                ctx,
                                product=product)
    else:
        await call_state_handler(AssortmentStates.ViewingAssortment,
                                ctx,
                                category=category,
                                current=current)

@router.message(AssortmentStates.ViewingProductDetails)
async def detailed_product_viewing_handler(_, ctx: Context) -> None:
    current: int = await ctx.fsm.get_value("current")
    category: int = await ctx.fsm.get_value("category")
    text = ctx.message.text
    if not text: return
    
    if text == ctx.t.UncategorizedTranslates.back:
        if current > await ctx.services.db.products.count_in_category(category): 
            await ctx.fsm.update_data(current=1)
            current = 1
        
        await call_state_handler(AssortmentStates.ViewingAssortment,
                                ctx,
                                category=category,
                                current=current)
        return
        
    product: Product = await ctx.services.db.products.find_by_category_and_index(category, current-1)
    if text == ctx.t.ReplyButtonsTranslates.Assortment.add_to_cart:
        await product.save_in_fsm(ctx, "product")
        await call_state_handler(AssortmentStates.FormingOrderEntry,
                                ctx,
                                product=product)
    else:
        await call_state_handler(AssortmentStates.ViewingProductDetails,
                                ctx,
                                product=product)

@router.message(AssortmentStates.FormingOrderEntry)
async def forming_order_entry_viewing_handler(_, ctx: Context) -> None:
    product: Product = await Product.from_fsm_context(ctx, "product")
    text = ctx.message.text
    if not text: return
    
    if text == ctx.t.UncategorizedTranslates.cancel:
        await call_state_handler(AssortmentStates.ViewingProductDetails,
                                ctx,
                                product=product)
    elif text == ctx.t.UncategorizedTranslates.finish:
        if await ctx.services.db.cart_entries.count_customer_cart_entries(ctx.customer) >= 10:
            await call_state_handler(AssortmentStates.MainMenu,
                                    ctx,
                                    send_before=(ctx.t.AssortmentTranslates.cant_add_to_cart_more, 1))
            return
        
        await ctx.services.db.cart_entries.add_to_cart(product, ctx.customer)
        await call_state_handler(CommonStates.MainMenu,
                                ctx,
                                send_before=(ctx.t.AssortmentTranslates.add_to_cart_finished, 1))
        
    elif text == ctx.t.ReplyButtonsTranslates.Assortment.extra_options:
        allowed_additionals = await ctx.services.db.additionals.get(product)
        await call_state_handler(AssortmentStates.AdditionalsEditing,
                                ctx,
                                product=product,
                                allowed_additionals=allowed_additionals)
    elif text in product.configuration.get_all_options_localized_names(ctx):
        idx, option = product.configuration.get_option_by_name(text, ctx)
        # \/\/\/\/\/\/\/\/ ВАЖНО, тк 0 == False
        if idx is not None: await ctx.fsm.update_data(current_option_key=idx)
        
        
        await option.save_in_fsm(ctx, "changing_option")
        await call_state_handler(AssortmentStates.EntryOptionSelect,
                                ctx,
                                product=product,
                                option=option)
    else:
        await call_state_handler(AssortmentStates.FormingOrderEntry,
                                ctx,
                                product=product)

@router.message(AssortmentStates.EntryOptionSelect)
async def entry_option_select(message: Message, ctx: Context) -> None:
    product: Product = await Product.from_fsm_context(ctx, "product")
    changing_option: ConfigurationOption = await ConfigurationOption.from_fsm_context(ctx, "changing_option")

    if message.text == ctx.t.UncategorizedTranslates.back:
        base_product: Product = await ctx.services.db.products.find_one_by_id(product.id)
        product.configuration.update(base_product.configuration, await ctx.services.db.additionals.get(product))

        await product.save_in_fsm(ctx, "product")
        
        await call_state_handler(AssortmentStates.FormingOrderEntry,
                                 ctx,
                                 product=product)
        return
    
    text = message.text.strip("\u0336🔒>< ").replace("\u0336", "").replace("\u00a0", " ").strip()
    choice = changing_option.get_by_name(text, ctx) or changing_option.get_by_name(text.rsplit(" ", 1)[0], ctx)


    if isinstance(choice, ConfigurationChoice):
        if choice.check_blocked_all(product.configuration.options):
            await call_state_handler(AssortmentStates.EntryOptionSelect,
                                    ctx,
                                    send_before=(ctx.t.AssortmentTranslates.cannot_choose.format(path=AssortmentTextGen.gen_blocked_choice_path_text(choice, product.configuration, ctx)), 1),
                                    product=product,
                                    option=changing_option)
            return
        
        if not choice.existing_presets and not choice.is_custom_input:
            changing_option.set_chosen(choice)

            current_option_key = await ctx.fsm.get_value("current_option_key")
            product.configuration.options[current_option_key] = changing_option
            product.configuration.update_price()
            
            await product.save_in_fsm(ctx, "product")
            await call_state_handler(AssortmentStates.EntryOptionSelect,
                                     ctx,
                                     product=product,
                                     option=changing_option)
            return
        else:
            await changing_option.save_in_fsm(ctx, "before_option")
            changing_option.set_chosen(choice)
            await changing_option.save_in_fsm(ctx, "changing_option")
            
            await call_state_handler(AssortmentStates.ChoiceEditValue,
                                     ctx,
                                     choice=choice)

    elif isinstance(choice, ConfigurationSwitches):
        await choice.save_in_fsm(ctx, "switches")
        await call_state_handler(AssortmentStates.SwitchesEditing,
                                    ctx,
                                    switches=choice,
                                    configuration=product.configuration)
    elif isinstance(choice, ConfigurationAnnotation):
        await call_state_handler(AssortmentStates.EntryOptionSelect,
                                    ctx,
                                    product=product,
                                    option=changing_option,
                                    annotation=choice)
    else:
        await call_state_handler(AssortmentStates.EntryOptionSelect,
                                    ctx,
                                    product=product,
                                    option=changing_option)


@router.message(AssortmentStates.SwitchesEditing)
async def switches_handler(message: Message, ctx: Context) -> None:
    product: Product = await Product.from_fsm_context(ctx, "product")
    
    if message.text == ctx.t.UncategorizedTranslates.back:
        option: ConfigurationOption = await ConfigurationOption.from_fsm_context(ctx, "changing_option")
        await call_state_handler(AssortmentStates.EntryOptionSelect,
                                 ctx,
                                 product=product,
                                 option=option)

        return

    switches: ConfigurationSwitches = await ConfigurationSwitches.from_fsm_context(ctx, "switches")
    
    if text := message.text:
        clean_text = text.strip("\u0336🔒✅ ").replace("\u0336", "").replace("\u00a0", " ").strip()
        switch = switches.get_by_localized_name(clean_text, ctx)
        if switch is None:
            await call_state_handler(AssortmentStates.SwitchesEditing,
                                ctx,
                                switches=switches,
                                configuration=product.configuration)
            return
        
        if switch.check_blocked_all(product.configuration.options):
            await call_state_handler(AssortmentStates.SwitchesEditing,
                                ctx,
                                switches=switches,
                                configuration=product.configuration,
                                send_before=(ctx.t.AssortmentTranslates.cannot_choose.format(path=AssortmentTextGen.gen_blocked_choice_path_text(switch, product.configuration, ctx)), 1))

            return
        
        switch.toggle()
        
        current_option_key = await ctx.fsm.get_value("current_option_key")

        option: ConfigurationOption = product.configuration.options[current_option_key] # ссылка на текущую изменяемую главную опцию
        key = option.get_key_by_name(switches.name.get(ctx), ctx)
        option.choices[key] = switches
        
        product.configuration.update_price()

        await product.save_in_fsm(ctx, "product")
        await option.save_in_fsm(ctx, "changing_option")
        await switches.save_in_fsm(ctx, "switches")

    await call_state_handler(AssortmentStates.SwitchesEditing,
                                ctx,
                                switches=switches,
                                configuration=product.configuration)

@router.message(AssortmentStates.AdditionalsEditing)
async def additionals_handler(message: Message, ctx: Context) -> None:
    product: Product = await Product.from_fsm_context(ctx, "product")
    text = message.text
    if not text: return

    if text == ctx.t.UncategorizedTranslates.back:
        await call_state_handler(AssortmentStates.FormingOrderEntry,
                                 ctx,
                                 product=product)

        return

    allowed_additionals = await ctx.services.db.additionals.get(product)
    if text:
        text = text.replace(" ✅", "")
        additional = ctx.services.db.additionals.get_by_name(text, allowed_additionals, ctx)
        if not additional:
            await call_state_handler(AssortmentStates.AdditionalsEditing,
                                    ctx, 
                                    product=product,
                                    allowed_additionals=allowed_additionals)
            return
            

        additionals = product.configuration.additionals
        if additional in additionals:
            additionals.remove(additional)
        else:
            additionals.append(additional)

        product.configuration.update_price()
        await product.save_in_fsm(ctx, "product")

    await call_state_handler(AssortmentStates.AdditionalsEditing,
                                ctx,
                                product=product,
                                allowed_additionals=allowed_additionals)

@router.callback_query(AssortmentStates.ChoiceEditValue)
async def choice_edit_value(callback: CallbackQuery, ctx: Context) -> None:
    if callback.data != "cancel": return

    before_option = await ctx.fsm.get_value("before_option")
    await ctx.fsm.update_data(changing_option=before_option)
    changing_option = ConfigurationOption(**before_option)

    await call_state_handler(AssortmentStates.EntryOptionSelect,
                             ctx,
                             product=await Product.from_fsm_context(ctx, "product"),
                             delete_prev=True,
                             option=changing_option)

    await callback.answer()

@router.message(AssortmentStates.ChoiceEditValue)
async def advanced_edit_value(message: Message, ctx: Context) -> None:
    text = await ctx.parse_user_input()
    if not text: return
    
    product: Product = await Product.from_fsm_context(ctx, "product")
    changing_option: ConfigurationOption = await ConfigurationOption.from_fsm_context(ctx, "changing_option")
    chosen = changing_option.get_chosen() # ССЫЛКА на объект, не надо дополнительно переприсваивать дочерних тварей

    if chosen.existing_presets:
        text = text.upper()
        if not chosen.validate_existing_preset(text):
            await message.delete()
            return
        chosen.set_chosen_preset(text)

        current_option_key = await ctx.fsm.get_value("current_option_key")
        product.configuration.options[current_option_key] = changing_option

        product.configuration.update_price()
        await product.save_in_fsm(ctx, "product")
        await call_state_handler(AssortmentStates.EntryOptionSelect,
                                 ctx,
                                 product=product,
                                 option=changing_option)
    elif chosen.is_custom_input:
        if text.isdigit():
            await message.delete()
            return
        chosen.custom_input_text = text

        current_option_key = await ctx.fsm.get_value("current_option_key")
        product.configuration.options[current_option_key] = changing_option

        product.configuration.update_price()
        await product.save_in_fsm(ctx, "product")
        await call_state_handler(AssortmentStates.EntryOptionSelect,
                                 ctx,
                                 product=product,
                                 option=changing_option)


# @router.message(Command("test"))
# async def cancel_handler(message: Message, state: FSMContext) -> None:
#     await state.clear()

#     await message.answer_invoice("Плоти денге",
#                                  "описалса",
#                                  "idхуйди",
#                                  currency="rub",
#                                  prices=[
#                                      LabeledPrice(label="Базовая цена", amount=10000),
#                                      LabeledPrice(label="скидка", amount=-1000)
#                                  ],
#                                  provider_token="1744374395:TEST:2c5a6f30c2763af47ad6",
#                                  need_shipping_address=True)


# @router.pre_checkout_query()
# async def on_pre_checkout_query(
#         pre_checkout_query: PreCheckoutQuery,
# ):
#     await pre_checkout_query.answer(ok=True)


# @router.message(F.successful_payment)
# async def on_successful_payment(
#         message: Message,
# ):
#     await message.reply(
#         "YAY",
#         # Это эффект "огонь" из стандартных реакций
#         message_effect_id="5104841245755180586"
#     )
