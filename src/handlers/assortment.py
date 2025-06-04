from typing import Optional
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import PreCheckoutQuery, Message, LabeledPrice, CallbackQuery, InputMediaPhoto, ReplyKeyboardRemove, \
    InlineKeyboardMarkup, ReplyKeyboardMarkup, InputMediaVideo

from src.classes import keyboards
from src.classes.db import DB
from src.classes.db_models import Product, ConfigurationOption, ConfigurationChoice, ConfigurationSwitches
from src.classes.keyboards import AssortmentKBs, CommonKBs, UncategorizedKBs
from src.classes.states import Assortment, CommonStates, MainMenuOptions
from src.classes.texts import generate_viewing_assortment_entry_caption, generate_product_detailed_caption, \
    generate_product_configurating_main, generate_choice_text, generate_presets_text, generate_cutom_input_text, \
    generate_switches_text, generate_additionals_text
from src.classes.translates import CommonTranslates, AssortmentTranslates, \
    UncategorizedTranslates

router = Router(name="assortment")

async def clear_keyboard_effect(message: Message) -> None:
    """Удаляет клавиатуру, скрыто."""
    msg = await message.answer("||BOO||", reply_markup=ReplyKeyboardRemove(), parse_mode="MarkdownV2")
    await msg.delete()

async def send_media_response(
    message: Message,
    media_id: Optional[str],
    caption: str,
    keyboard: Optional[InlineKeyboardMarkup | ReplyKeyboardMarkup] = None,
    media_type: str = "photo"
) -> None:
    if media_type == "photo":
        await message.answer_photo(media_id, caption=caption, reply_markup=keyboard)
    elif media_type == "video":
        await message.answer_video(media_id, caption=caption, reply_markup=keyboard)
    else:
        await message.answer(caption, reply_markup=keyboard)

async def edit_media_message(
    message: Message,
    media_id: str,
    caption: str,
    reply_markup: Optional[InlineKeyboardMarkup | ReplyKeyboardMarkup] = None,
    media_type: str = "photo"
) -> None:
    """Редактирование медиа-сообщения"""
    media = InputMediaPhoto(media=media_id, caption=caption) if media_type == 'photo' else InputMediaVideo(media=media_id, caption=caption)
    await message.edit_media(media=media, reply_markup=reply_markup)

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
async def assortment_category_handler(message: Message, state: FSMContext, db: DB, lang: str) -> None:
    if message.text in UncategorizedTranslates.back.values():
        await message.answer(CommonTranslates.translate("heres_the_menu", lang),
                             reply_markup=CommonKBs.main_menu(lang))
        await state.set_state(CommonStates.main_menu)
        return

    category = next(
        (category.name for category in await db.categories.get_all()
         if category.localized_name.data[lang] == message.text),
        None  # значение по умолчанию, если ничего не найдено
    )

    if not category:
        await message.answer(AssortmentTranslates.translate("cant_find_that_category", lang),
                             reply_markup=await AssortmentKBs.assortment_menu(db, lang))
        return

    total = await db.get_count_by_query(Product, {"category": category})

    if total == 0:
        await message.answer(
            AssortmentTranslates.translate("no_products_in_category", lang),
            reply_markup=await AssortmentKBs.assortment_menu(db, lang))
        return

    product: Product = await db.products.find_one_by({'order_no': 1, "category": category})

    await clear_keyboard_effect(message)

    currency = UncategorizedTranslates.translate("currency_sign", lang)
    caption = generate_viewing_assortment_entry_caption(product, currency, lang)

    await send_media_response(message,
                              product.short_description_photo_id,
                              caption,
                              AssortmentKBs.gen_assortment_view_kb(1, total, lang))

    await state.set_data({})
    await state.update_data(current=1, category=category, amount=total)
    await state.set_state(Assortment.ViewingAssortment)

@router.callback_query(Assortment.ViewingAssortment)
async def assortment_viewing_handler(callback: CallbackQuery, state: FSMContext, db: DB, lang: str) -> None:

    match callback.data:
        case "back":
            await callback.message.answer(AssortmentTranslates.translate("choose_the_category", lang),
                                          reply_markup=await AssortmentKBs.assortment_menu(db, lang))
            await callback.message.delete()
            await state.set_data({})
            await state.set_state(MainMenuOptions.Assortment)
        case "view_left" | "view_right":
            current = await state.get_value("current")
            amount = await state.get_value("amount")
            category = await state.get_value("category")

            new_order = 1
            if callback.data == 'view_left':
                new_order = amount if current == 1 else current - 1
            elif callback.data == 'view_right':
                new_order = 1 if current == amount else current + 1

            product = await db.products.find_one_by({'order_no': new_order, 'category': category})
            caption = generate_viewing_assortment_entry_caption(product,
                                                                UncategorizedTranslates.translate("currency_sign", lang),
                                                                lang)

            await edit_media_message(callback.message,
                                     product.short_description_photo_id,
                                     caption,
                                     AssortmentKBs.gen_assortment_view_kb(new_order, amount, lang))

            await state.update_data(current=new_order)
            await state.set_state(Assortment.ViewingAssortment)

        case "details":
            current = await state.get_value("current")
            category = await state.get_value("category")

            product = await db.products.find_one_by({'order_no': current, 'category': category})
            currency = UncategorizedTranslates.translate("currency_sign", lang)
            caption = generate_product_detailed_caption(product, currency, lang)

            await edit_media_message(callback.message,
                                     product.long_description_photo_id,
                                     caption,
                                     AssortmentKBs.detailed_view(lang))

            await state.set_state(Assortment.ViewingProductDetails)



    await callback.answer()

@router.callback_query(Assortment.ViewingProductDetails)
async def detailed_product_viewing_handler(callback: CallbackQuery, state: FSMContext, db: DB, lang: str) -> None:
    current: int = await state.get_value("current")
    category: int = await state.get_value("category")
    amount: int = await state.get_value("amount")
    product = await db.products.find_one_by({'order_no': current, "category": category})
    currency_sign = UncategorizedTranslates.translate("currency_sign", lang)

    match callback.data:
        case "back":
            caption = generate_viewing_assortment_entry_caption(product, currency_sign, lang)

            await edit_media_message(callback.message,
                                     product.short_description_photo_id,
                                     caption,
                                     AssortmentKBs.gen_assortment_view_kb(current, amount, lang))

            await state.set_state(Assortment.ViewingAssortment)

        case "add_to_cart":
            options: dict[str, ConfigurationOption] = product.configuration.options
            photo_id = product.configuration_photo_id
            video_id = product.configuration_video_id

            await callback.message.delete()
            await state.update_data(product=product.model_dump())

            additionals = await db.additionals.get(product.category, product.id)

            await send_media_response(callback.message,
                                      photo_id if photo_id else video_id,
                                      generate_product_configurating_main(product, lang),
                                      AssortmentKBs.adding_to_cart_main(options, len(additionals)>0, lang),
                                      "photo" if photo_id else ("video" if video_id else None))

            await state.set_state(Assortment.FormingOrderEntry)

    await callback.answer()

@router.callback_query(Assortment.FormingOrderEntry)
async def forming_order_entry_viewing_handler(callback: CallbackQuery, state: FSMContext, db: DB, lang: str) -> None:
    current: int = await state.get_value("current")
    category: int = await state.get_value("category")
    product = await db.products.find_one_by({'order_no': current, "category": category})
    cached_product = Product(**await state.get_value("product"))
    currency_sign = UncategorizedTranslates.translate("currency_sign", lang)

    match callback.data:
        case "cancel":
            caption = generate_product_detailed_caption(product, currency_sign, lang)

            await callback.message.delete()

            await send_media_response(callback.message,
                                      product.long_description_photo_id,
                                      caption,
                                      AssortmentKBs.detailed_view(lang)
                                      )

            await state.update_data(product=None)
            await state.set_state(Assortment.ViewingProductDetails)
        case "finish":
            pass
        case "additional_view":
            allowed_additionals = await db.additionals.get(cached_product.category, cached_product.id)
            additionals = cached_product.configuration.additionals

            text = generate_additionals_text(allowed_additionals, additionals, lang)
            kb = AssortmentKBs.generate_additionals_kb(allowed_additionals, additionals, lang)

            await callback.message.delete()

            await callback.message.answer(
                text,
                reply_markup=kb
            )
            await state.set_state(Assortment.AdditionalsEditing)
        case _ if callback.data in [option.name.data[lang] for option in product.configuration.options.values()]:
            key, option = next((key, option) for key, option in cached_product.configuration.options.items()
                                               if option.name.data[lang] == callback.data)

            await callback.message.delete()

            await process_chosen_option(callback.message, option, lang)

            await state.update_data(changing_option=option.model_dump())
            await state.update_data(current_option_key=key)
            await state.set_state(Assortment.EntryOptionSelect)

    await callback.answer()

@router.message(Assortment.EntryOptionSelect)
async def entry_option_select(message: Message, state: FSMContext, lang: str, db) -> None:
    cached_product = Product(**await state.get_value("product"))
    changing_option = ConfigurationOption(**await state.get_value("changing_option"))
    currency_sign = UncategorizedTranslates.translate("currency_sign", lang)

    if message.text == UncategorizedTranslates.translate("back", lang):
        options: dict[str, ConfigurationOption] = cached_product.configuration.options
        photo_id = cached_product.configuration_photo_id
        video_id = cached_product.configuration_video_id

        await state.update_data(product=cached_product.model_dump())

        await clear_keyboard_effect(message)

        additionals = await db.additionals.get(cached_product.category, cached_product.id)

        await send_media_response(message,
                                  photo_id or video_id,
                                  generate_product_configurating_main(cached_product,
                                                                      lang),
                                  AssortmentKBs.adding_to_cart_main(options, len(additionals)>0, lang),
                                  "photo" if photo_id else ("video" if video_id else None)
                                  )

        await state.set_state(Assortment.FormingOrderEntry)
        return
    choice = next(choice for choice in changing_option.choices
                                       if choice.label.data[lang] == message.text.replace(">", "").replace("<", ""))

    if isinstance(choice, ConfigurationChoice):
        if not choice.existing_presets and not choice.is_custom_input:
            changing_option.chosen = changing_option.choices.index(choice)+1

            current_option_key = await state.get_value("current_option_key")
            cached_product.configuration.options[current_option_key] = changing_option

            await process_chosen_option(message, changing_option, lang)

            await state.update_data(product=cached_product.model_dump())
            await state.update_data(changing_option=changing_option.model_dump())
            return
        else:
            chosen = changing_option.choices[changing_option.choices.index(choice)]
            await state.update_data(before_option=changing_option.model_dump())
            changing_option.chosen = changing_option.choices.index(choice)+1

            await clear_keyboard_effect(message)

            text = generate_presets_text(chosen, lang) if choice.existing_presets else generate_cutom_input_text(chosen, lang)
            kb = UncategorizedKBs.inline_cancel(lang)

            await send_media_response(message,
                                      chosen.photo_id or chosen.video_id,
                                      text,
                                      kb,
                                      "photo" if chosen.photo_id else ("video" if chosen.video_id else None)
                                      )

            await state.update_data(changing_option=changing_option.model_dump())
            await state.set_state(Assortment.ChoiceEditValue)

    elif isinstance(choice, ConfigurationSwitches):
        switches: ConfigurationSwitches = choice

        await clear_keyboard_effect(message)

        text = generate_switches_text(switches, lang)
        kb = AssortmentKBs.generate_switches_kb(switches, lang)

        await send_media_response(message,
                                  switches.photo_id or switches.video_id,
                                  text,
                                  kb,
                                  "photo" if switches.photo_id else ("video" if switches.video_id else None)
                                  )
        await state.update_data(switches=switches.model_dump())
        await state.set_state(Assortment.SwitchesEditing)

@router.message(Assortment.SwitchesEditing)
async def switches_handler(message: Message, state: FSMContext, lang: str) -> None:
    if message.text == UncategorizedTranslates.translate("back", lang):
        option: ConfigurationOption = ConfigurationOption(**await state.get_value("changing_option"))

        await process_chosen_option(message, option, lang)

        await state.update_data(changing_option=option.model_dump())
        await state.set_state(Assortment.EntryOptionSelect)
        return

    cached_product = Product(**await state.get_value("product"))
    changing_option = ConfigurationOption(**await state.get_value("changing_option"))
    switches = ConfigurationSwitches(**await state.get_value("switches"))

    switch_text = message.text.replace(" ✅", "")
    switch, index = next((s, i) for i, s in enumerate(switches.switches) if s.name.data[lang] == switch_text)
    switch.enabled = not switch.enabled
    switches.switches[index] = switch

    text = generate_switches_text(switches, lang)
    kb = AssortmentKBs.generate_switches_kb(switches, lang)

    await send_media_response(message,
                              switches.photo_id or switches.video_id,
                              text,
                              kb,
                              "photo" if switches.photo_id else ("video" if switches.video_id else None)
                              )

    current_option_key = await state.get_value("current_option_key")

    index = next(i for i, choice in enumerate(changing_option.choices)
                 if choice.label.data[lang] == switches.label.data[lang])

    changing_option.choices[index] = switches
    cached_product.configuration.options[current_option_key].choices[index] = switches

    await state.update_data(product=cached_product.model_dump())
    await state.update_data(changing_option=changing_option.model_dump())
    await state.update_data(switches=switches.model_dump())


@router.message(Assortment.AdditionalsEditing)
async def additionals_handler(message: Message, state: FSMContext, lang: str, db) -> None:
    cached_product = Product(**await state.get_value("product"))

    if message.text == UncategorizedTranslates.translate("back", lang):
        options: dict[str, ConfigurationOption] = cached_product.configuration.options
        photo_id = cached_product.configuration_photo_id
        video_id = cached_product.configuration_video_id

        await state.update_data(product=cached_product.model_dump())

        await clear_keyboard_effect(message)

        additionals = await db.additionals.get(cached_product.category, cached_product.id)

        await send_media_response(message,
                                  photo_id or video_id,
                                  generate_product_configurating_main(cached_product,
                                                                      lang),
                                  AssortmentKBs.adding_to_cart_main(options, len(additionals) > 0, lang),
                                  "photo" if photo_id else ("video" if video_id else None)
                                  )

        await state.set_state(Assortment.FormingOrderEntry)
        return

    allowed_additionals = await db.additionals.get(cached_product.category, cached_product.id)
    additionals = cached_product.configuration.additionals

    additional_text = message.text.replace(" ✅", "")
    additional, index = next((a, i) for i, a in enumerate(allowed_additionals) if a.name.data[lang] == additional_text)

    if additional in additionals:
        additionals.remove(additional)
    else:
        additionals.append(additional)


    text = generate_additionals_text(allowed_additionals, additionals, lang)
    kb = AssortmentKBs.generate_additionals_kb(allowed_additionals, additionals, lang)

    await message.answer(
        text,
        reply_markup=kb
    )

    cached_product.configuration.additionals = additionals

    await state.update_data(product=cached_product.model_dump())

@router.callback_query(Assortment.ChoiceEditValue)
async def choice_edit_value(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    if callback.data != "cancel": return

    changing_option = ConfigurationOption(**await state.get_value("before_option"))
    chosen = changing_option.choices[changing_option.chosen - 1]

    text = generate_choice_text(changing_option, lang)
    kb = AssortmentKBs.generate_choice_kb(changing_option, lang)

    await send_media_response(callback.message,
                              chosen.photo_id or chosen.video_id,
                              text,
                              kb,
                              "photo" if chosen.photo_id else "video" if chosen.video_id else None
                              )

    await state.update_data(changing_option=changing_option.model_dump())
    await state.set_state(Assortment.EntryOptionSelect)
    await callback.answer()

@router.message(Assortment.ChoiceEditValue)
async def advanced_edit_value(message: Message, state: FSMContext, lang: str) -> None:
    cached_product = Product(**await state.get_value("product"))
    changing_option = ConfigurationOption(**await state.get_value("changing_option"))
    chosen = changing_option.choices[changing_option.chosen - 1]

    if chosen.existing_presets:
        allowed_range = list(range(1, chosen.existing_presets_quantity+1))
        if not message.text.isdigit() or int(message.text) not in allowed_range:
            await message.delete()
            return
        chosen.existing_presets_chosen = int(message.text)

        changing_option.choices[changing_option.chosen-1] = chosen

        current_option_key = await state.get_value("current_option_key")
        cached_product.configuration.options[current_option_key] = changing_option


        await process_chosen_option(message, changing_option, lang)

        await state.update_data(product=cached_product.model_dump())
        await state.update_data(changing_option=changing_option.model_dump())
        await state.set_state(Assortment.EntryOptionSelect)
    elif chosen.is_custom_input:
        if message.text.isdigit():
            await message.delete()
            return
        chosen.custom_input_text = message.text

        changing_option.choices[changing_option.chosen - 1] = chosen

        current_option_key = await state.get_value("current_option_key")
        cached_product.configuration.options[current_option_key] = changing_option

        await process_chosen_option(message, changing_option, lang)

        await state.update_data(product=cached_product.model_dump())
        await state.update_data(changing_option=changing_option.model_dump())
        await state.set_state(Assortment.EntryOptionSelect)

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
