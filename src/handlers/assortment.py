from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, LabeledPrice, CallbackQuery

from ui.texts import AssortmentTextGen
from core.helper_classes import Context
from schemas.db_models import *
from schemas.db_schemas import *
from core.states import Assortment, CommonStates, call_state_handler
from ui.translates import *

router = Router(name="assortment")

@router.message(CommonStates.MainMenu, lambda message: (message.text in ReplyButtonsTranslates.assortment.values()) if message.text else False)
async def assortment_command_handler(_, ctx: Context) -> None:
    await call_state_handler(Assortment.Menu, ctx)

@router.message(Assortment.Menu)
async def assortment_category_handler(message: Message, ctx: Context) -> None:
    if message.text in UncategorizedTranslates.back.values():
        await call_state_handler(CommonStates.MainMenu,
                                 ctx)
        return

    category = next(
        (category.name for category in await ctx.db.categories.get_all()
         if category.localized_name.get(ctx.lang) == message.text),
        None  # значение по умолчанию, если ничего не найдено
    )

    if not category:
        await call_state_handler(Assortment.Menu, ctx)
        return

    await ctx.fsm.update_data(category=category, current=1)
    await call_state_handler(Assortment.ViewingAssortment,
                             ctx,
                             edit=False,
                             category=category,
                             current=1)

@router.message(Assortment.ViewingAssortment)
async def assortment_viewing_handler(_, ctx: Context) -> None:
    text = ctx.message.text
    
    if text == UncategorizedTranslates.translate("back", ctx.lang):
        await call_state_handler(Assortment.Menu,
                                ctx)
        return
    
    current = await ctx.fsm.get_value("current") or 1
    category = await ctx.fsm.get_value("category")
    amount = await ctx.db.products.count_in_category(category)
    
    if text in ["⬅️", "➡️"]:
        if text == '⬅️':
            new_order = amount if current == 1 else current - 1
        elif text == '➡️':
            new_order = 1 if current == amount else current + 1
            
        await ctx.fsm.update_data(current=new_order, category=category)
        await call_state_handler(Assortment.ViewingAssortment,
                                ctx,
                                category=category,
                                current=new_order)
    elif text == ReplyButtonsTranslates.Assortment.translate("details", ctx.lang):
        if amount == 0: 
            await ctx.message.delete()
            return
        
        await ctx.fsm.update_data(product=None)
        
        product: Product = await ctx.db.products.get_by_category_and_index(category, current-1)
        await call_state_handler(Assortment.ViewingProductDetails,
                                ctx,
                                product=product)
    else:
        await call_state_handler(Assortment.ViewingAssortment,
                                ctx,
                                category=category,
                                current=current)

@router.message(Assortment.ViewingProductDetails)
async def detailed_product_viewing_handler(_, ctx: Context) -> None:
    current: int = await ctx.fsm.get_value("current")
    category: int = await ctx.fsm.get_value("category")
    text = ctx.message.text
    
    if text == UncategorizedTranslates.translate("back", ctx.lang):
        if current > await ctx.db.products.count_in_category(category): 
            await ctx.fsm.update_data(current=1)
            current = 1
        
        await call_state_handler(Assortment.ViewingAssortment,
                                ctx,
                                category=category,
                                current=current)
        return
        
    product: Product = await ctx.db.products.get_by_category_and_index(category, current-1)
    if text == ReplyButtonsTranslates.Assortment.translate("add_to_cart", ctx.lang):
        await ctx.fsm.update_data(product=product.model_dump())
        await call_state_handler(Assortment.FormingOrderEntry,
                                ctx,
                                product=product)
    else:
        await call_state_handler(Assortment.ViewingProductDetails,
                                ctx,
                                product=product)

@router.message(Assortment.FormingOrderEntry)
async def forming_order_entry_viewing_handler(_, ctx: Context) -> None:
    product = Product(**await ctx.fsm.get_value("product"))
    text = ctx.message.text
    
    if text == UncategorizedTranslates.translate("cancel", ctx.lang):
        await call_state_handler(Assortment.ViewingProductDetails,
                                ctx,
                                product=product)
    elif text == UncategorizedTranslates.translate("finish", ctx.lang):
        
        await ctx.db.cart_entries.add_to_cart(product, ctx.customer)
        await call_state_handler(CommonStates.MainMenu,
                                ctx,
                                send_before=(AssortmentTranslates.translate("add_to_cart_finished", ctx.lang), 1))
        
    elif text == "+":
        allowed_additionals = await ctx.db.additionals.get(product)
        await call_state_handler(Assortment.AdditionalsEditing,
                                ctx,
                                product=product,
                                allowed_additionals=allowed_additionals)
    elif text in product.configuration.get_all_options_localized_names(ctx.lang):
        idx, option = product.configuration.get_option_by_name(text, ctx.lang)
        # \/\/\/\/\/\/\/\/ ВАЖНО, тк 0 == False
        if idx is not None: await ctx.fsm.update_data(current_option_key=idx)
        
        
        await ctx.fsm.update_data(changing_option=option.model_dump())
        await call_state_handler(Assortment.EntryOptionSelect,
                                ctx,
                                product=product,
                                option=option)
    else:
        await call_state_handler(Assortment.FormingOrderEntry,
                                ctx,
                                product=product)

@router.message(Assortment.EntryOptionSelect)
async def entry_option_select(message: Message, ctx: Context) -> None:
    product = Product(**await ctx.fsm.get_value("product"))
    changing_option = ConfigurationOption(**await ctx.fsm.get_value("changing_option"))

    if message.text == UncategorizedTranslates.translate("back", ctx.lang):
        base_product = await ctx.db.products.find_one_by_id(product.id)
        product.configuration.update(base_product.configuration, await ctx.db.additionals.get(product))

        await ctx.fsm.update_data(product=product.model_dump())
        
        await call_state_handler(Assortment.FormingOrderEntry,
                                 ctx,
                                 product=product)
        return
    
    text = message.text.strip("\u0336🔒>< ").replace("\u0336", "").replace("\u00a0", " ").strip()
    choice = changing_option.get_by_label(text, ctx.lang) or changing_option.get_by_label(text.rsplit(" ", 1)[0], ctx.lang)


    if isinstance(choice, ConfigurationChoice):
        if choice.check_blocked_all(product.configuration.options):
            await call_state_handler(Assortment.EntryOptionSelect,
                                    ctx,
                                    send_before=(AssortmentTranslates.translate("cannot_choose", ctx.lang).format(path=AssortmentTextGen.gen_blocked_choice_path_text(choice, product.configuration, ctx.lang)), 1),
                                    product=product,
                                    option=changing_option)
            return
        
        if not choice.existing_presets and not choice.is_custom_input:
            changing_option.set_chosen(choice)

            current_option_key = await ctx.fsm.get_value("current_option_key")
            product.configuration.options[current_option_key] = changing_option
            product.configuration.update_price()
            
            await ctx.fsm.update_data(product=product.model_dump())
            await call_state_handler(Assortment.EntryOptionSelect,
                                     ctx,
                                     product=product,
                                     option=changing_option)
            return
        else:
            await ctx.fsm.update_data(before_option=changing_option.model_dump())
            changing_option.set_chosen(choice)
            await ctx.fsm.update_data(changing_option=changing_option.model_dump())
            
            await call_state_handler(Assortment.ChoiceEditValue,
                                     ctx,
                                     choice=choice)

    elif isinstance(choice, ConfigurationSwitches):
        await ctx.fsm.update_data(switches=choice.model_dump())
        await call_state_handler(Assortment.SwitchesEditing,
                                    ctx,
                                    switches=choice)
    else:
        await call_state_handler(Assortment.EntryOptionSelect,
                                    ctx,
                                    product=product,
                                    option=changing_option)


@router.message(Assortment.SwitchesEditing)
async def switches_handler(message: Message, ctx: Context) -> None:
    if message.text == UncategorizedTranslates.translate("back", ctx.lang):
        option: ConfigurationOption = ConfigurationOption(**await ctx.fsm.get_value("changing_option"))
        await call_state_handler(Assortment.EntryOptionSelect,
                                 ctx,
                                 product=Product(**await ctx.fsm.get_value("product")),
                                 option=option)

        return

    switches = ConfigurationSwitches(**await ctx.fsm.get_value("switches"))
    
    if text := message.text:
        clean_text = text.replace(" ✅", "")
        switches.toggle_by_localized_name(clean_text, ctx.lang)
        
        product = Product(**await ctx.fsm.get_value("product"))
        current_option_key = await ctx.fsm.get_value("current_option_key")

        option: ConfigurationOption = product.configuration.options[current_option_key] # ссылка на текущую изменяемую главную опцию
        key = option.get_key_by_label(switches.label.data.get(ctx.lang), ctx.lang)
        option.choices[key] = switches
        
        product.configuration.update_price()

        await ctx.fsm.update_data(product=product.model_dump())
        await ctx.fsm.update_data(changing_option=option.model_dump())
        await ctx.fsm.update_data(switches=switches.model_dump())

    await call_state_handler(Assortment.SwitchesEditing,
                                ctx,
                                switches=switches)

@router.message(Assortment.AdditionalsEditing)
async def additionals_handler(message: Message, ctx: Context) -> None:
    product = Product(**await ctx.fsm.get_value("product"))
    text = message.text

    if text == UncategorizedTranslates.translate("back", ctx.lang):
        await call_state_handler(Assortment.FormingOrderEntry,
                                 ctx,
                                 product=product)

        return

    allowed_additionals = await ctx.db.additionals.get(product)
    if text:
        text = ctx.message.text.replace(" ✅", "")
        additional = ctx.db.additionals.get_by_name(text, allowed_additionals, ctx.lang)
        if not additional:
            await call_state_handler(Assortment.AdditionalsEditing,
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
        await ctx.fsm.update_data(product=product.model_dump())

    await call_state_handler(Assortment.AdditionalsEditing,
                                ctx,
                                product=product,
                                allowed_additionals=allowed_additionals)

@router.callback_query(Assortment.ChoiceEditValue)
async def choice_edit_value(callback: CallbackQuery, ctx: Context) -> None:
    if callback.data != "cancel": return

    before_option = await ctx.fsm.get_value("before_option")
    await ctx.fsm.update_data(changing_option=before_option)
    changing_option = ConfigurationOption(**before_option)

    await call_state_handler(Assortment.EntryOptionSelect,
                             ctx,
                             product=Product(**await ctx.fsm.get_value("product")),
                             delete_prev=True,
                             option=changing_option)

    await callback.answer()

@router.message(Assortment.ChoiceEditValue)
async def advanced_edit_value(message: Message, ctx: Context) -> None:
    product = Product(**await ctx.fsm.get_value("product"))
    changing_option = ConfigurationOption(**await ctx.fsm.get_value("changing_option"))
    chosen = changing_option.get_chosen() # ССЫЛКА на объект, не надо дополнительно переприсваивать дочерних тварей

    if chosen.existing_presets:
        if not (message.text.isdigit() and 
                1 <= int(message.text) <= chosen.existing_presets_quantity):
            await message.delete()
            return
        chosen.existing_presets_chosen = int(message.text)

        current_option_key = await ctx.fsm.get_value("current_option_key")
        product.configuration.options[current_option_key] = changing_option

        product.configuration.update_price()
        await ctx.fsm.update_data(product=product.model_dump())
        await call_state_handler(Assortment.EntryOptionSelect,
                                 ctx,
                                 product=product,
                                 option=changing_option)
    elif chosen.is_custom_input:
        if message.text.isdigit():
            await message.delete()
            return
        chosen.custom_input_text = message.text

        current_option_key = await ctx.fsm.get_value("current_option_key")
        product.configuration.options[current_option_key] = changing_option

        product.configuration.update_price()
        await ctx.fsm.update_data(product=product.model_dump())
        await call_state_handler(Assortment.EntryOptionSelect,
                                 ctx,
                                 product=product,
                                 option=changing_option)


@router.message(Command("test"))
async def cancel_handler(message: Message, state: FSMContext) -> None:
    await state.clear()

    await message.answer_invoice("Плоти денге",
                                 "описалса",
                                 "idхуйди",
                                 currency="rub",
                                 prices=[
                                     LabeledPrice(label="Базовая цена", amount=10000),
                                     LabeledPrice(label="скидка", amount=-1000)
                                 ],
                                 provider_token="1744374395:TEST:2c5a6f30c2763af47ad6",
                                 need_shipping_address=True)


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
