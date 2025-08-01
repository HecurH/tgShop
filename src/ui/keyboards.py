from aiogram import types
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

from core.helper_classes import Context
from schemas.db_models import *
from schemas.types import LocalizedMoney
from ui.message_tools import strike
from ui.translates import ProfileTranslates, ReplyButtonsTranslates, UncategorizedTranslates

from configs.supported import SUPPORTED_CURRENCIES, SUPPORTED_LANGUAGES_TEXT

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
    def assortment_menu(categories: Iterable[Category], lang: str) -> types.ReplyKeyboardMarkup:
        builder = ReplyKeyboardBuilder()
        for category in categories:

            builder.add(types.KeyboardButton(text=category.localized_name.get(lang)))

        builder.adjust(2)
        builder.attach(ReplyKeyboardBuilder([[types.KeyboardButton(text=UncategorizedTranslates.translate("back", lang))]]))
        return builder.as_markup(
            resize_keyboard=True,
            #one_time_keyboard=True,
            input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", lang))

    @staticmethod
    def gen_assortment_view_kb(current: int, amount: int, lang) -> types.ReplyKeyboardMarkup:
        controls = [
            types.KeyboardButton(text="⬅️"),
            types.KeyboardButton(text=f"{current}/{amount}"),
            types.KeyboardButton(text="➡️")
        ] if amount > 1 else [
            types.KeyboardButton(text=f"{current}/{amount}")
        ]
        
        kb = [
            [
                types.KeyboardButton(text=ReplyButtonsTranslates.Assortment.translate("details", lang)
                                    )
            ],
            controls,
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
    def detailed_view(lang) -> types.ReplyKeyboardMarkup:
        kb = [
            [
                types.KeyboardButton(text=UncategorizedTranslates.translate("back", lang)),

                types.KeyboardButton(text=ReplyButtonsTranslates.Assortment.translate("add_to_cart", lang))
            ]
        ]
        return types.ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True,
            input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", lang))

    @staticmethod
    def adding_to_cart_main(options: dict[str, ConfigurationOption], has_additionals: bool,  lang) -> types.ReplyKeyboardMarkup:
        builder = ReplyKeyboardBuilder()
        for option in options.values():
            builder.add(
                types.KeyboardButton(
                    text=option.name.get(lang)
                )
            )
        builder.adjust(2)

        btns = [
            types.KeyboardButton(
                text=UncategorizedTranslates.translate("cancel", lang)
            )
        ]
        if has_additionals:
            btns.append(
                types.KeyboardButton(
                    text="+"
                )
            )
        btns.append(
            types.KeyboardButton(text=UncategorizedTranslates.translate("finish", lang))
        )

        markup = types.ReplyKeyboardMarkup(keyboard=
            [
                btns
            ]
        )
        builder.attach(ReplyKeyboardBuilder.from_markup(markup))

        return builder.as_markup(
            resize_keyboard=True,
            input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", lang))

    @staticmethod
    def generate_choice_kb(product: Product, option: ConfigurationOption, ctx: Context) -> types.ReplyKeyboardMarkup:
        builder = ReplyKeyboardBuilder()

        for choice in option.choices.values():
            price_text = f" {choice.price.to_text(ctx.customer.currency)}" if isinstance(choice, ConfigurationChoice) and choice.price.get_amount(ctx.customer.currency) != 0 else ""

            is_blocked = choice.check_blocked_all(product.configuration.options) if isinstance(choice, ConfigurationChoice) else False

            label = f"{strike(choice.label.get(ctx.lang) + price_text)} 🔒" if is_blocked else f"{choice.label.get(ctx.lang)}{price_text}"
            builder.add(types.KeyboardButton(text=f">{label}<"
                                            if option.get_chosen().label == choice.label
                                            else label))

        builder.adjust(3)

        builder.attach(ReplyKeyboardBuilder([
            [types.KeyboardButton(text=UncategorizedTranslates.translate("back", ctx.lang))]
        ]
        ))

        return builder.as_markup(
            resize_keyboard=True,
            # one_time_keyboard=True,
            input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", ctx.lang))

    @staticmethod
    def generate_switches_kb(switches: ConfigurationSwitches, lang: str) -> types.ReplyKeyboardMarkup:
        builder = ReplyKeyboardBuilder()

        for switch in switches.switches:
            label = switch.name.get(lang)
            builder.add(types.KeyboardButton(text=f"{label} ✅"
                                            if switch.enabled
                                            else label))
        builder.adjust(3)

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
            label = additional.name.get(lang)
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

class CartKBs:
    @staticmethod
    def cart_view(entry: CartEntry, current: int, amount: int, cart_price: LocalizedMoney, ctx: Context) -> types.ReplyKeyboardMarkup:
        controls = [
            types.KeyboardButton(text="⬅️"),
            types.KeyboardButton(text=f"{current}/{amount}"),
            types.KeyboardButton(text="➡️")
        ] if amount > 1 else [
            types.KeyboardButton(text=f"{current}/{amount}")
        ]
        
        kb = [
            [
                types.KeyboardButton(text='❌'),
                types.KeyboardButton(text="➖"),
                types.KeyboardButton(text=f"{entry.quantity} {UncategorizedTranslates.translate('unit', ctx.lang, count=entry.quantity)}"),
                types.KeyboardButton(text="➕")
            ],
            controls,
            [
                types.KeyboardButton(text=UncategorizedTranslates.translate("back", ctx.lang)),
                types.KeyboardButton(text=ReplyButtonsTranslates.Cart.translate("place", ctx.lang).format(price=cart_price.to_text(ctx.customer.currency)))
            ]
        ]

        return types.ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True,
            input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", ctx.lang)
        )
    
    @staticmethod
    def cart_order_configuration(has_bonus_money: bool, used_bonus_money: bool, total_price: LocalizedMoney, ctx: Context) -> types.ReplyKeyboardMarkup:
        use_promocode = ReplyButtonsTranslates.Cart.OrderConfiguration.translate("use_promocode", ctx.lang)
        use_bonus_money = ReplyButtonsTranslates.Cart.OrderConfiguration.translate("use_bonus_money", ctx.lang)
        place = ReplyButtonsTranslates.Cart.translate("place", ctx.lang)
        change_payment_method = ReplyButtonsTranslates.Cart.translate("change_payment_method", ctx.lang)
        
        first_line = [
            types.KeyboardButton(text=use_promocode),
            types.KeyboardButton(
                text=f"{use_bonus_money} ✅" if has_bonus_money and used_bonus_money
                else (use_bonus_money if has_bonus_money else f"{strike(use_bonus_money)} 🔒")
            )
        ]
        
        kb = [
            first_line,
            [
                types.KeyboardButton(text=change_payment_method)
            ],
            [
                types.KeyboardButton(text=UncategorizedTranslates.translate("back", ctx.lang)),
                types.KeyboardButton(text=place.format(price=total_price.to_text(ctx.currency)))
            ]
        ]

        return types.ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True,
            input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", ctx.lang)
        )
        

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
                ReplyButtonsTranslates.Profile.Delivery.Edit.translate("foreign", lang) + (" ✅"
                if delivery_info.is_foreign else " ❌")
            )

            # Клавиатура, если сервис доставки выбран
            if delivery_info.service:
                keyboard = [
                    [
                        types.KeyboardButton(text=foreign_text),
                        types.KeyboardButton(text=delivery_info.service.name.get(lang))
                    ],
                    [
                        types.KeyboardButton(text=delivery_info.service.selected_option.name.get(lang)),
                        types.KeyboardButton(text=ReplyButtonsTranslates.Profile.Delivery.Edit.translate("change_data", lang))
                    ],
                    [
                        types.KeyboardButton(text=UncategorizedTranslates.translate("back", lang)),
                        types.KeyboardButton(text=ReplyButtonsTranslates.Profile.Delivery.Edit.translate("delete", lang))
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
        
        @staticmethod
        def delete_confimation(lang) -> types.ReplyKeyboardMarkup:
            keyboard = [
                [
                    types.KeyboardButton(text=UncategorizedTranslates.translate("no", lang)),
                    types.KeyboardButton(text=UncategorizedTranslates.translate("yes", lang))
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
                        types.KeyboardButton(text=UncategorizedTranslates.translate("back" if first_setup else "cancel", lang))
                    ]
                ]
                return types.ReplyKeyboardMarkup(
                    keyboard=keyboard,
                    resize_keyboard=True,
                    input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", lang)
                )
                
            @staticmethod
            def services(first_setup: bool, services: Iterable[DeliveryService], customer: Customer, lang) -> types.ReplyKeyboardMarkup:
                builder = ReplyKeyboardBuilder()
            
                for service in services:
                    builder.add(types.KeyboardButton(text=f"{service.name.get(lang)} ({service.price.to_text(customer.currency)})"))

                builder.adjust(2)
                
                
                keyboard = [
                    [
                        types.KeyboardButton(text=UncategorizedTranslates.translate("back" if first_setup else "cancel", lang))
                    ]
                ]
                builder.attach(ReplyKeyboardBuilder(keyboard))
                
                return types.ReplyKeyboardMarkup(
                    keyboard=builder.export(),
                    resize_keyboard=True,
                    input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", lang)
                )
            
            @staticmethod
            def requirements_lists(first_setup: bool, lists: list[DeliveryRequirementsList], lang) -> types.ReplyKeyboardMarkup:
                builder = ReplyKeyboardBuilder()
            
                for lst in lists:
                    builder.add(types.KeyboardButton(text=lst.name.get(lang)))

                builder.adjust(2)
                
                
                keyboard = [
                    [
                        types.KeyboardButton(text=UncategorizedTranslates.translate("back" if first_setup else "cancel", lang))
                    ]
                ]
                builder.attach(ReplyKeyboardBuilder(keyboard))
                
                return types.ReplyKeyboardMarkup(
                    keyboard=builder.export(),
                    resize_keyboard=True,
                    input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", lang)
                )
            
            @staticmethod
            def requirement(first_setup: bool, lang) -> types.ReplyKeyboardMarkup:
                keyboard = [
                    [
                        types.KeyboardButton(text=UncategorizedTranslates.translate("back" if first_setup else "cancel", lang))
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
    
    @staticmethod
    def yes_no(lang) -> types.ReplyKeyboardMarkup:
        kb = [
            [
                types.KeyboardButton(text=UncategorizedTranslates.translate("no", lang)),
                types.KeyboardButton(text=UncategorizedTranslates.translate("yes", lang))
            ]
        ]
        
        return types.ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True,
            input_field_placeholder=ReplyButtonsTranslates.translate("choose_an_item", lang)
        )

