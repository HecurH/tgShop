
from aiogram.fsm.state import StatesGroup, State


class CommonStates(StatesGroup):
    main_menu = State()
    choosing_food_size = State()