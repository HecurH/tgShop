from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import PreCheckoutQuery, Message, LabeledPrice, CallbackQuery

from src.classes.helper_classes import Context
from src.classes.message_tools import send_media_response
from src.classes.db_models import Product, ConfigurationOption, ConfigurationChoice, ConfigurationSwitches
from src.classes.keyboards import AssortmentKBs
from src.classes.states import Assortment, CommonStates, MainMenuOptions, call_state_handler
from src.classes.texts import generate_choice_text
from src.classes.translates import AssortmentTranslates, UncategorizedTranslates

router = Router(name="assortment")


async def process_chosen_option(
        message: Message,
        option: ConfigurationOption,
        lang: str
):
    chosen = option.choices[option.chosen - 1]
    text = generate_choice_text(option, lang)
    kb = AssortmentKBs.generate_choice_kb(option, lang)

    await send_media_response(message, chosen.photo_id or chosen.video_id, text, kb,
                              media_type="video" if chosen.video_id else "photo" if chosen.photo_id else "text")


@router.message(MainMenuOptions.Assortment)
async def assortment_category_handler(message: Message, ctx: Context) -> None:
    if message.text in UncategorizedTranslates.back.values():
        await call_state_handler(CommonStates.main_menu,
                                 ctx)
        return

    category = next(
        (category.name for category in await ctx.db.categories.get_all()
         if category.localized_name.data[ctx.lang] == message.text),
        None  # значение по умолчанию, если ничего не найдено
    )

    if not category:
        await message.answer(AssortmentTranslates.translate("cant_find_that_category", ctx.lang),
                             reply_markup=await AssortmentKBs.assortment_menu(ctx.db, ctx.lang))
        return

    amount = await ctx.db.get_count_by_query(Product, {"category": category})

    await call_state_handler(Assortment.ViewingAssortment,
                             ctx,
                             edit=False,
                             category=category,
                             current=1,
                             amount=amount)


@router.callback_query(Assortment.ViewingAssortment)
async def assortment_viewing_handler(callback: CallbackQuery, ctx: Context) -> None:
    match callback.data:
        case "back":
            await call_state_handler(MainMenuOptions.Assortment,
                                     ctx)
        case "view_left" | "view_right":
            current = await ctx.fsm.get_value("current")
            amount = await ctx.fsm.get_value("amount")
            category = await ctx.fsm.get_value("category")

            new_order = 1
            if callback.data == 'view_left':
                new_order = amount if current == 1 else current - 1
            elif callback.data == 'view_right':
                new_order = 1 if current == amount else current + 1

            await call_state_handler(Assortment.ViewingAssortment,
                                     ctx,
                                     edit=True,
                                     category=category,
                                     current=new_order,
                                     amount=amount)

        case "details":
            current = await ctx.fsm.get_value("current")
            category = await ctx.fsm.get_value("category")

            product = await ctx.db.products.find_one_by({'order_no': current, 'category': category})

            await call_state_handler(Assortment.ViewingProductDetails,
                                     ctx,
                                     product=product)

    await callback.answer()


@router.callback_query(Assortment.ViewingProductDetails)
async def detailed_product_viewing_handler(callback: CallbackQuery, ctx: Context) -> None:
    current: int = await ctx.fsm.get_value("current")
    category: int = await ctx.fsm.get_value("category")
    amount: int = await ctx.fsm.get_value("amount")
    product = await ctx.db.products.find_one_by({'order_no': current, "category": category})

    match callback.data:
        case "back":
            await call_state_handler(Assortment.ViewingAssortment,
                                     ctx,
                                     edit=True,
                                     category=category,
                                     current=current,
                                     amount=amount)

        case "add_to_cart":

            await call_state_handler(Assortment.FormingOrderEntry,
                                     ctx,
                                     edit=True,  # тк вызов из инлайна
                                     product=product)

    await callback.answer()


@router.callback_query(Assortment.FormingOrderEntry)
async def forming_order_entry_viewing_handler(callback: CallbackQuery, ctx: Context) -> None:
    cached_product = Product(**await ctx.fsm.get_value("product"))

    match callback.data:
        case "cancel":
            await call_state_handler(Assortment.ViewingProductDetails,
                                     ctx,
                                     product=cached_product)
        case "finish":
            pass
        case "additional_view":
            await call_state_handler(Assortment.AdditionalsEditing,
                                     ctx,
                                     product=cached_product)
        case _ if callback.data in cached_product.configuration.get_all_options_localized_names(ctx.lang):
            
            idx, option = cached_product.configuration.get_option_by_name(callback.data, ctx.lang)

            await call_state_handler(Assortment.EntryOptionSelect,
                                     ctx,
                                     delete_prev=True,
                                     option=option,
                                     idx=idx)

    await callback.answer()


@router.message(Assortment.EntryOptionSelect)
async def entry_option_select(message: Message, ctx: Context) -> None:
    cached_product = Product(**await ctx.fsm.get_value("product"))
    changing_option = ConfigurationOption(**await ctx.fsm.get_value("changing_option"))

    if message.text == UncategorizedTranslates.translate("back", ctx.lang):
        await call_state_handler(Assortment.FormingOrderEntry,
                                 ctx,
                                 edit=False,  # вызов из реплая
                                 product=cached_product)
        return
    
    choice = changing_option.get_by_label(message.text.replace(">", "").replace("<", ""), ctx.lang)

    if isinstance(choice, ConfigurationChoice):
        if not choice.existing_presets and not choice.is_custom_input:
            changing_option.set_chosen(choice)

            current_option_idx = await ctx.fsm.get_value("current_option_idx")
            cached_product.configuration.options[current_option_idx] = changing_option

            await call_state_handler(Assortment.EntryOptionSelect,
                                     ctx,
                                     delete_prev=False,
                                     option=changing_option)
            await ctx.fsm.update_data(product=cached_product.model_dump())
            return
        else:
            await call_state_handler(Assortment.ChoiceEditValue,
                                     ctx,
                                     changing_option=changing_option,
                                     choice=choice)

    elif isinstance(choice, ConfigurationSwitches):
        
        await call_state_handler(Assortment.SwitchesEditing,
                                    ctx,
                                    switches=choice)


@router.message(Assortment.SwitchesEditing)
async def switches_handler(message: Message, ctx: Context) -> None:
    if message.text == UncategorizedTranslates.translate("back", ctx.lang):
        option: ConfigurationOption = ConfigurationOption(**await ctx.fsm.get_value("changing_option"))

        await call_state_handler(Assortment.EntryOptionSelect,
                                 ctx,
                                 delete_prev=False,
                                 option=option)

        return

    switches = ConfigurationSwitches(**await ctx.fsm.get_value("switches"))

    await call_state_handler(Assortment.SwitchesEditing,
                                ctx,
                                switches=switches,
                                switch_text=message.text)


@router.message(Assortment.AdditionalsEditing)
async def additionals_handler(message: Message, ctx: Context) -> None:
    cached_product = Product(**await ctx.fsm.get_value("product"))

    if message.text == UncategorizedTranslates.translate("back", ctx.lang):
        await call_state_handler(Assortment.FormingOrderEntry,
                                 ctx,
                                 edit=False,  # тк вызов из реплая
                                 product=cached_product)

        return

    await call_state_handler(Assortment.AdditionalsEditing,
                                ctx,
                                product=cached_product,
                                additional_text=message.text)


@router.callback_query(Assortment.ChoiceEditValue)
async def choice_edit_value(callback: CallbackQuery, ctx: Context) -> None:
    if callback.data != "cancel": return

    changing_option = ConfigurationOption(**await ctx.fsm.get_value("before_option"))

    await call_state_handler(Assortment.EntryOptionSelect,
                             ctx,
                             delete_prev=True,
                             option=changing_option)

    await callback.answer()


@router.message(Assortment.ChoiceEditValue)
async def advanced_edit_value(message: Message, ctx: Context) -> None:
    cached_product = Product(**await ctx.fsm.get_value("product"))
    changing_option = ConfigurationOption(**await ctx.fsm.get_value("changing_option"))
    chosen = changing_option.get_chosen() # ССЫЛКА на объект, не надо дополнительно переприсваивать дочерних тварей

    if chosen.existing_presets:
        if not (message.text.isdigit() and 
                1 <= int(message.text) <= chosen.existing_presets_quantity):
            await message.delete()
            return
        chosen.existing_presets_chosen = int(message.text)

        current_option_idx = await ctx.fsm.get_value("current_option_idx")
        cached_product.configuration.options[current_option_idx] = changing_option

        await ctx.fsm.update_data(product=cached_product.model_dump())
        await call_state_handler(Assortment.EntryOptionSelect,
                                 ctx,
                                 delete_prev=False,
                                 option=changing_option)
    elif chosen.is_custom_input:
        if message.text.isdigit():
            await message.delete()
            return
        chosen.custom_input_text = message.text

        current_option_idx = await ctx.fsm.get_value("current_option_idx")
        cached_product.configuration.options[current_option_idx] = changing_option

        await ctx.fsm.update_data(product=cached_product.model_dump())
        await call_state_handler(Assortment.EntryOptionSelect,
                                 ctx,
                                 delete_prev=False,
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


@router.pre_checkout_query()
async def on_pre_checkout_query(
        pre_checkout_query: PreCheckoutQuery,
):
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(
        message: Message,
):
    await message.reply(
        "YAY",
        # Это эффект "огонь" из стандартных реакций
        message_effect_id="5104841245755180586"
    )
