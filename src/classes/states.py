from aiogram.fsm.state import StatesGroup, State


class CommonStates(StatesGroup):
    lang_choosing = State()
    main_menu = State()


class ShopStates(StatesGroup):
    Assortment = State()
    ViewingAssortment = State()

    Cart = State()
    Orders = State()
