from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import PreCheckoutQuery, Message, LabeledPrice

from src.classes import keyboards
from src.classes.db import DB
from src.classes.states import ShopStates, CommonStates
from src.classes.translates import CommonTranslates, ReplyButtonsTranslates, AssortmentTranslates, \
    UncategorizedTranslates

router = Router(name="shopping")


@router.message(CommonStates.main_menu, lambda message: message.text in ReplyButtonsTranslates.assortment.values())
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
    await message.answer(category,
                         reply_markup=await keyboards.assortment_menu(db, lang))


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