from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import PreCheckoutQuery, Message, LabeledPrice, CallbackQuery, InputMediaPhoto, ReplyKeyboardRemove
from pydantic_mongo.pagination import Edge

from src.classes import keyboards
from src.classes.db import DB
from src.classes.db_models import Product
from src.classes.states import ShopStates, CommonStates
from src.classes.translates import CommonTranslates, ReplyButtonsTranslates, AssortmentTranslates, \
    UncategorizedTranslates

router = Router(name="shopping")


@router.message(CommonStates.main_menu, lambda message: (message.text in ReplyButtonsTranslates.assortment.values()) if message.text else False)
async def assortment_command_handler(message: Message, state: FSMContext, db: DB,  lang: str) -> None:
    await message.answer(AssortmentTranslates.translate("choose_the_category", lang),
                         reply_markup=await keyboards.assortment_menu(db, lang))
    await state.set_state(ShopStates.Assortment)

@router.message(ShopStates.Assortment)
async def assortment_category_handler(message: Message, state: FSMContext, db: DB,  lang: str) -> None:
    if message.text in UncategorizedTranslates.back.values():
        await message.answer(CommonTranslates.translate("heres_the_menu", lang),
                             reply_markup=keyboards.main_menu(lang))
        await state.set_state(CommonStates.main_menu)
        return

    categories = [category.name for category in await db.categories.get_all()]
    category = AssortmentTranslates.get_attribute(message.text, lang)

    if not category or category not in categories:
        await message.answer(AssortmentTranslates.translate("cant_find_that_category", lang),
                             reply_markup=await keyboards.assortment_menu(db, lang))
        return

    amount = await db.get_count_by_query(Product, {"category": category})


    if amount == 0:
        await message.answer(AssortmentTranslates.translate("no_products_in_category", lang), reply_markup=await keyboards.assortment_menu(db, lang))
        return


    product: Product = await db.products.find_one_by({'order_no': 1, "category": category})

    msg = await message.answer("_BOO_",
                         reply_markup=ReplyKeyboardRemove(), parse_mode="Markdown")
    await msg.delete()

    await message.answer_photo(product.short_description_photo_id,
                               f"{product.name.data[lang]} - {product.short_description.data[lang]}",
                         reply_markup=keyboards.gen_assortment_view_kb(1, amount, lang))

    await state.set_data({})

    await state.update_data(current=1)
    await state.update_data(category=category)
    await state.update_data(amount=amount)

    await state.set_state(ShopStates.ViewingAssortment)


@router.callback_query(ShopStates.ViewingAssortment)
async def assortment_viewing_handler(callback: CallbackQuery, state: FSMContext, db: DB, lang: str) -> None:

    if callback.data == "back":
        await callback.message.answer(AssortmentTranslates.translate("choose_the_category", lang),
                             reply_markup=await keyboards.assortment_menu(db, lang))
        await callback.message.delete()
        await state.set_data({})
        await state.set_state(ShopStates.Assortment)

    elif callback.data == "view_left":
        current: int = await state.get_value("current")
        category: int = await state.get_value("category")
        amount: int = await state.get_value("amount")

        if current == 1:
            product = await db.products.find_one_by({'order_no': amount, "category": category})


            await callback.message.edit_media(InputMediaPhoto(media=product.short_description_photo_id,
                                              caption=f"{product.name.data[lang]} - {product.short_description.data[lang]}"),
                reply_markup=keyboards.gen_assortment_view_kb(amount, amount, lang))

            await state.update_data(current=amount)
            await state.set_state(ShopStates.ViewingAssortment)
            await callback.answer()
            return

        product = await db.products.find_one_by({'order_no': current-1, "category": category})


        await callback.message.edit_media(InputMediaPhoto(media=product.short_description_photo_id, caption=f"{product.name.data[lang]} - {product.short_description.data[lang]}"), reply_markup=keyboards.gen_assortment_view_kb(current-1, amount, lang))


        await state.update_data(current=current-1)
        await state.set_state(ShopStates.ViewingAssortment)
    elif callback.data == "view_right":
        current: int = await state.get_value("current")
        category: int = await state.get_value("category")
        amount: int = await state.get_value("amount")

        if current == amount:
            product = await db.products.find_one_by({'order_no': 1, "category": category})


            await callback.message.edit_media(InputMediaPhoto(media=product.short_description_photo_id,
                                              caption=f"{product.name.data[lang]} - {product.short_description.data[lang]}"),
                reply_markup=keyboards.gen_assortment_view_kb(1, amount, lang))

            await state.update_data(current=1)
            await state.set_state(ShopStates.ViewingAssortment)
            await callback.answer()
            return

        product = await db.products.find_one_by({'order_no': current+1, "category": category})


        await callback.message.edit_media(InputMediaPhoto(media=product.short_description_photo_id, caption=f"{product.name.data[lang]} - {product.short_description.data[lang]}"), reply_markup=keyboards.gen_assortment_view_kb(current+1, amount, lang))


        await state.update_data(current=current+1)
        await state.set_state(ShopStates.ViewingAssortment)
    elif callback.data == "details":
        current: int = await state.get_value("current")
        category: int = await state.get_value("category")
        amount: int = await state.get_value("amount")

        product = await db.products.find_one_by({'order_no': current, "category": category})

        await callback.message.edit_media(
            InputMediaPhoto(media=product.long_description_photo_id,
                            caption=f"{product.name.data[lang]} \n\n{product.long_description.data[lang]}"),
            reply_markup=keyboards.detailed_view(lang))


        await state.set_state(ShopStates.ViewingProductDetails)


    await callback.answer()

@router.callback_query(ShopStates.ViewingProductDetails)
async def assortment_viewing_handler(callback: CallbackQuery, state: FSMContext, db: DB, lang: str) -> None:

    if callback.data == "back":
        current: int = await state.get_value("current")
        category: int = await state.get_value("category")
        amount: int = await state.get_value("amount")
        product = await db.products.find_one_by({'order_no': current, "category": category})


        await callback.message.edit_media(InputMediaPhoto(media=product.short_description_photo_id,
                                                          caption=f"{product.name.data[lang]} - {product.short_description.data[lang]}"),
                                          reply_markup=keyboards.gen_assortment_view_kb(current, amount, lang))

        await state.set_state(ShopStates.ViewingAssortment)


    await callback.answer()


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
    print(message)
    await message.reply(
        "YAY",
        # Это эффект "огонь" из стандартных реакций
        message_effect_id="5104841245755180586"
    )