from aiogram.fsm.state import StatesGroup, State


class CommonStates(StatesGroup):
    lang_choosing = State()
    main_menu = State()

class MainMenuOptions(StatesGroup):
    Assortment = State()
    Cart = State()
    Orders = State()

class Assortment(StatesGroup):
    ViewingAssortment = State()
    ViewingProductDetails = State()
    FormingOrderEntry = State()
    EntryOptionSelect = State()
    ChoiceEditValue = State()
    SwitchesEditing = State()

    AdditionalsEditing = State()

