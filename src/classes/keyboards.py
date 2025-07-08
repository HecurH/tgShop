from aiogram import types
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

from src.classes.db import DB
from src.classes.db_models import *
from src.classes.translates import ProfileTranslates, ReplyButtonsTranslates, UncategorizedTranslates, \
    InlineButtonsTranslates

from src.classes.config import SUPPORTED_CURRENCIES, SUPPORTED_LANGUAGES_TEXT

class CommonKBs:

    @staticmethod
    def lang_choose() -> types.InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        
        for key, value in SUPPORTED_LANGUAGES_TEXT.items():
            builder.add(types.InlineKeyboardButton(text=key, callback_data=value))

        builder.adjust(2)
        return builder.as_markup()
    
    @staticmethod
    def currency_choose(lang) -> types.InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        
        for currency in SUPPORTED_CURRENCIES.keys():
            builder.add(types.InlineKeyboardButton(text=f"{UncategorizedTranslates.Currencies.translate(currency, lang)}", callback_data=currency))

        builder.adjust(2)
        return builder.as_markup()

    @staticmethod
    def main_menu(lang: str) -> types.ReplyKeyboardMarkup:
        kb = [
            [
                types.KeyboardButton(text=ReplyButtonsTranslates.translate("assortment", lang)),
                types.KeyboardButton(text=ReplyButtonsTranslates.translate("cart", lang))
            ],
            [
                types.KeyboardButton(text=ReplyButtonsTranslates.translate("orders", lang)),
                types.KeyboardButton(text=ReplyButtonsTranslates.translate("about", lang))
            ],
            [
                types.KeyboardButton(text=ReplyButtonsTranslates.translate("profile", lang))
            ]
        ]
        return types.ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True,
            input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", lang)
        )

class AssortmentKBs:

    @staticmethod
    async def assortment_menu(db: DB, lang: str) -> types.ReplyKeyboardMarkup:
        builder = ReplyKeyboardBuilder()
        for category in await db.categories.get_all():

            builder.add(types.KeyboardButton(text=category.localized_name.data[lang]))

        builder.adjust(2)
        builder.attach(ReplyKeyboardBuilder([[types.KeyboardButton(text=UncategorizedTranslates.translate("back", lang))]]))
        return builder.as_markup(
            resize_keyboard=True,
            #one_time_keyboard=True,
            input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", lang))

    @staticmethod
    def gen_assortment_view_kb(current: int, amount: int, lang) -> types.InlineKeyboardMarkup:
        kb = [
            [
                types.InlineKeyboardButton(text=InlineButtonsTranslates.translate("details", lang),
                                            callback_data="details" if amount != 0 else "none")
            ],
            [
                types.InlineKeyboardButton(text="⬅️" if amount > 1 else "❌",
                                            callback_data="view_left" if amount > 1 else "none"),

                types.InlineKeyboardButton(text=f"{current}/{amount}",
                                            callback_data="none"),

                types.InlineKeyboardButton(text="➡️" if amount > 1 else "❌",
                                            callback_data="view_right" if amount > 1 else "none")
            ],
            [
                types.InlineKeyboardButton(text=UncategorizedTranslates.translate("back", lang), callback_data="back")
            ]
        ]
        return types.InlineKeyboardMarkup(
            inline_keyboard=kb
        )

    @staticmethod
    def detailed_view(lang) -> types.InlineKeyboardMarkup:
        kb = [
            [
                types.InlineKeyboardButton(text=UncategorizedTranslates.translate("back", lang),
                                            callback_data="back"),

                types.InlineKeyboardButton(text=InlineButtonsTranslates.translate("add_to_cart", lang),
                                            callback_data="add_to_cart")
            ]
        ]
        return types.InlineKeyboardMarkup(
            inline_keyboard=kb
        )

    @staticmethod
    def adding_to_cart_main(configurations: list[ConfigurationOption], has_additionals: bool,  lang) -> types.InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        for option in configurations:
            builder.add(
                types.InlineKeyboardButton(
                    text=option.name.data[lang],
                    callback_data=option.name.data[lang]
                )
            )
        builder.adjust(2)

        btns = [
            types.InlineKeyboardButton(
                text=UncategorizedTranslates.translate("cancel", lang),
                callback_data="cancel",
            )
        ]
        if has_additionals:
            btns.append(
                types.InlineKeyboardButton(
                    text="+",
                    callback_data="additional_view")
            )
        btns.append(
            types.InlineKeyboardButton(
                text=UncategorizedTranslates.translate("finish", lang),
                callback_data="finish")
        )

        markup = types.InlineKeyboardMarkup(inline_keyboard=
                                            [
                                                btns
                                            ]
                                        )
        builder.attach(InlineKeyboardBuilder.from_markup(markup))

        return builder.as_markup()

    @staticmethod
    def generate_choice_kb(option: ConfigurationOption, lang: str) -> types.ReplyKeyboardMarkup:
        builder = ReplyKeyboardBuilder()

        for choice in option.choices:
            label = choice.label.data[lang]
            builder.add(types.KeyboardButton(text=f">{label}<"
                                            if option.choices[option.chosen-1].label == choice.label
                                            else label))

        builder.attach(ReplyKeyboardBuilder([
            [types.KeyboardButton(text=UncategorizedTranslates.translate("back", lang))]
        ]
        ))

        return builder.as_markup(
            resize_keyboard=True,
            # one_time_keyboard=True,
            input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", lang))

    @staticmethod
    def generate_switches_kb(switches: ConfigurationSwitches, lang: str) -> types.ReplyKeyboardMarkup:
        builder = ReplyKeyboardBuilder()

        for switch in switches.switches:
            label = switch.name.data[lang]
            builder.add(types.KeyboardButton(text=f"{label} ✅"
                                            if switch.enabled
                                            else label))

        builder.attach(ReplyKeyboardBuilder([
            [types.KeyboardButton(text=UncategorizedTranslates.translate("back", lang))]
        ]
        ))

        return builder.as_markup(
            resize_keyboard=True,
            # one_time_keyboard=True,
            input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", lang))

    @staticmethod
    def generate_additionals_kb(available_additionals: list[ProductAdditional], additionals: list[ProductAdditional], lang: str):
        builder = ReplyKeyboardBuilder()

        for additional in available_additionals:
            label = additional.name.data[lang]
            builder.add(types.KeyboardButton(text=f"{label} ✅"
                                            if additional in additionals
                                            else label))

        builder.attach(ReplyKeyboardBuilder([
            [types.KeyboardButton(text=UncategorizedTranslates.translate("back", lang))]
        ]
        ))

        return builder.as_markup(
            resize_keyboard=True,
            # one_time_keyboard=True,
            input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", lang))


class ProfileKBs:
    
    @staticmethod
    def menu(lang) -> types.ReplyKeyboardMarkup:
        kb = [
            [
                types.KeyboardButton(text=ReplyButtonsTranslates.Profile.translate("settings", lang))
            ],
            [
                types.KeyboardButton(text=ReplyButtonsTranslates.Profile.translate("referrals", lang)),
                types.KeyboardButton(text=ReplyButtonsTranslates.Profile.translate("delivery", lang))
            ],
            [
                types.KeyboardButton(text=UncategorizedTranslates.translate("back", lang))
            ]
            
        ]
        return types.ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True,
            input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", lang)
        )
    
    class Settings:
    
        @staticmethod
        def menu(lang) -> types.ReplyKeyboardMarkup:
            kb = [
                [
                    types.KeyboardButton(text=ReplyButtonsTranslates.Profile.Settings.translate("lang", lang)),
                    types.KeyboardButton(text=ReplyButtonsTranslates.Profile.Settings.translate("currency", lang))
                ],
                [
                    types.KeyboardButton(text=UncategorizedTranslates.translate("back", lang))
                ]
                
            ]
            return types.ReplyKeyboardMarkup(
                keyboard=kb,
                resize_keyboard=True,
                input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", lang)
            )
        
        @staticmethod
        def lang_choose(lang) -> types.ReplyKeyboardMarkup:
            builder = ReplyKeyboardBuilder()
            for key in SUPPORTED_LANGUAGES_TEXT.keys():

                builder.add(types.KeyboardButton(text=key))

            builder.adjust(2)
            builder.attach(ReplyKeyboardBuilder([[types.KeyboardButton(text=UncategorizedTranslates.translate("back", lang))]]))
            return builder.as_markup(
                resize_keyboard=True,
                input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", lang))
        
        @staticmethod
        def currency_choose(lang) -> types.ReplyKeyboardMarkup:
            builder = ReplyKeyboardBuilder()
            for key in SUPPORTED_CURRENCIES.keys():

                builder.add(types.KeyboardButton(text=UncategorizedTranslates.Currencies.translate(key, lang)))

            builder.adjust(2)
            builder.attach(ReplyKeyboardBuilder([[types.KeyboardButton(text=UncategorizedTranslates.translate("back", lang))]]))
            return builder.as_markup(
                resize_keyboard=True,
                input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", lang))
    
    class Delivery:
        
        @staticmethod
        def menu(delivery_info: DeliveryInfo, lang) -> types.ReplyKeyboardMarkup:
            # Текст для иностранной доставки
            foreign_text = (
                ReplyButtonsTranslates.Profile.Delivery.Edit.translate("foreign", lang) + "✅"
                if delivery_info.is_foreign else "❌"
            )

            # Клавиатура, если сервис доставки выбран
            if delivery_info.service:
                keyboard = [
                    [
                        types.KeyboardButton(text=foreign_text),
                        types.KeyboardButton(text=delivery_info.service.name[lang])
                    ],
                    [
                        types.KeyboardButton(text=delivery_info.service.selected_option.name[lang]),
                        types.KeyboardButton(text=ReplyButtonsTranslates.Profile.Delivery.Edit.translate("change_data", lang))
                    ],
                    [
                        types.KeyboardButton(text=UncategorizedTranslates.translate("back", lang))
                    ]
                ]
            else:
                keyboard = [
                    [
                        types.KeyboardButton(text=ReplyButtonsTranslates.Profile.Delivery.translate("menu_not_set", lang))
                    ],
                    [
                        types.KeyboardButton(text=UncategorizedTranslates.translate("back", lang))
                    ]
                ]

            return types.ReplyKeyboardMarkup(
                keyboard=keyboard,
                resize_keyboard=True,
                input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", lang)
            )
        
        class Editables:
            
            
            @staticmethod
            def is_foreign(first_setup: bool, lang) -> types.ReplyKeyboardMarkup:
                keyboard = [
                    [
                        types.KeyboardButton(text=ProfileTranslates.Delivery.translate("foreign_choice_rus", lang)),
                        types.KeyboardButton(text=ProfileTranslates.Delivery.translate("foreign_choice_foreign", lang))
                    ],
                    [
                        types.KeyboardButton(text=UncategorizedTranslates.translate("cancel" if first_setup else "back", lang))
                    ]
                ]
                return types.ReplyKeyboardMarkup(
                    keyboard=keyboard,
                    resize_keyboard=True,
                    input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", lang)
                )
        
        
    
    class Balance:
            
        @staticmethod
        def change_currency(current_currency: str, lang) -> types.ReplyKeyboardMarkup:
            builder = ReplyKeyboardBuilder()
            for currency in [cur for cur in SUPPORTED_CURRENCIES.keys() if cur != current_currency]:
                builder.add(types.KeyboardButton(text=currency))

            builder.adjust(2)
            
            markup = types.ReplyKeyboardMarkup(keyboard=
                                            [[
                                                types.KeyboardButton(text=UncategorizedTranslates.translate("back", lang))
                                            ]]
                                        )
            builder.attach(ReplyKeyboardBuilder.from_markup(markup))
            
            return builder.as_markup(
                resize_keyboard=True,
                #one_time_keyboard=True,
                input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", lang))
    
class UncategorizedKBs:
    @staticmethod
    def inline_back(lang) -> types.InlineKeyboardMarkup:
        kb = [
            [
                types.InlineKeyboardButton(text=UncategorizedTranslates.translate("back", lang), callback_data="back")
            ]
        ]
        return types.InlineKeyboardMarkup(
            inline_keyboard=kb
        )

    @staticmethod
    def inline_cancel(lang) -> types.InlineKeyboardMarkup:
        kb = [
            [
                types.InlineKeyboardButton(text=UncategorizedTranslates.translate("cancel", lang), callback_data="cancel")
            ]
        ]
        return types.InlineKeyboardMarkup(
            inline_keyboard=kb
        )

