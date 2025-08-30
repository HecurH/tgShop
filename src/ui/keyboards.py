from aiogram import types
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

from configs.payments import SUPPORTED_PAYMENT_METHODS
from core.helper_classes import Context
from schemas.db_models import *
from schemas.types import LocalizedMoney
from ui.message_tools import strike

from configs.supported import SUPPORTED_CURRENCIES, SUPPORTED_LANGUAGES_TEXT
from ui.translates import ReplyButtonsTranslates

class CommonKBs:

    @staticmethod
    def lang_choose() -> types.InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        
        for display_text, code in SUPPORTED_LANGUAGES_TEXT.items():
            builder.add(types.InlineKeyboardButton(text=display_text, callback_data=code))

        builder.adjust(2)
        return builder.as_markup()
    
    @staticmethod
    def currency_choose(ctx: Context) -> types.InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        
        for currency in SUPPORTED_CURRENCIES.keys():
            builder.add(types.InlineKeyboardButton(text=getattr(ctx.t.UncategorizedTranslates.Currencies, currency), callback_data=currency))

        builder.adjust(2)
        return builder.as_markup()

    @staticmethod
    def main_menu(ctx: Context) -> types.ReplyKeyboardMarkup:
        kb = [
            [
                types.KeyboardButton(text=ctx.t.ReplyButtonsTranslates.assortment),
                types.KeyboardButton(text=ctx.t.ReplyButtonsTranslates.cart)
            ],
            [
                types.KeyboardButton(text=ctx.t.ReplyButtonsTranslates.orders),
                types.KeyboardButton(text=ctx.t.ReplyButtonsTranslates.about)
            ],
            [
                types.KeyboardButton(text=ctx.t.ReplyButtonsTranslates.profile)
            ]
        ]
        return types.ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True,
            input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item
        )

class AdminKBs:
    class Orders:
        
        @staticmethod
        async def price_confirmation(order: Order, ctx: Context) -> types.InlineKeyboardMarkup:
            me = await ctx.message.bot.get_me()
            keyboard = [
                [
                    types.InlineKeyboardButton(
                        text="Спросить у клиента",
                        url=f"tg://resolve?domain={me.username}&start=admin_msg_to_{ctx.customer.user_id}"
                    )
                ],
                [
                    types.InlineKeyboardButton(
                        text="Расформировать заказ",
                        url=f"tg://resolve?domain={me.username}&start=admin_unform_order_{order.id}"
                    ),
                    types.InlineKeyboardButton(
                        text="Назначить цену",
                        url=f"tg://resolve?domain={me.username}&start=admin_confirm_price_{order.id}"
                    )
                ]
            ]
            return types.InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        @staticmethod
        def manual_payment_confirmation(order: Order, ctx: Context) -> types.InlineKeyboardMarkup:
            keyboard = [
                [
                    types.InlineKeyboardButton(
                        text="Подтвердить оплату ✅",
                        callback_data=f"confirm_manual_payment_{str(order.id)}"
                    )
                ]
            ]
            return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


class AssortmentKBs:

    @staticmethod
    def assortment_menu(categories: Iterable[Category], ctx: Context) -> types.ReplyKeyboardMarkup:
        builder = ReplyKeyboardBuilder()
        for category in categories:

            builder.add(types.KeyboardButton(text=category.localized_name.get(ctx.lang)))

        builder.adjust(2)
        builder.attach(ReplyKeyboardBuilder([[types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back)]]))
        return builder.as_markup(
            resize_keyboard=True,
            #one_time_keyboard=True,
            input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item)

    @staticmethod
    def gen_assortment_view_kb(current: int, amount: int, ctx: Context) -> types.ReplyKeyboardMarkup:
        controls = [
            types.KeyboardButton(text="⬅️"),
            types.KeyboardButton(text=f"{current}/{amount}"),
            types.KeyboardButton(text="➡️")
        ] if amount > 1 else [
            types.KeyboardButton(text=f"{current}/{amount}")
        ]
        
        kb = [
            [
                types.KeyboardButton(text=ctx.t.ReplyButtonsTranslates.Assortment.details)
            ],
            controls,
            [
                types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back)
            ]
        ]
        
        return types.ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True,
            input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item
        )

    @staticmethod
    def detailed_view(ctx: Context) -> types.ReplyKeyboardMarkup:
        kb = [
            [
                types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back),

                types.KeyboardButton(text=ctx.t.ReplyButtonsTranslates.Assortment.add_to_cart)
            ]
        ]
        return types.ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True,
            input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item)

    @staticmethod
    def adding_to_cart_main(options: dict[str, ConfigurationOption], has_additionals: bool, ctx: Context) -> types.ReplyKeyboardMarkup:
        builder = ReplyKeyboardBuilder()
        for option in options.values():
            builder.add(
                types.KeyboardButton(
                    text=option.name.get(ctx.lang)
                )
            )
        builder.adjust(2)

        btns = [
            types.KeyboardButton(
                text=ctx.t.UncategorizedTranslates.cancel
            )
        ]
        if has_additionals:
            btns.append(
                types.KeyboardButton(
                    text="+"
                )
            )
        btns.append(
            types.KeyboardButton(text=ctx.t.UncategorizedTranslates.finish)
        )

        markup = types.ReplyKeyboardMarkup(keyboard=
            [
                btns
            ]
        )
        builder.attach(ReplyKeyboardBuilder.from_markup(markup))

        return builder.as_markup(
            resize_keyboard=True,
            input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item)

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
            [types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back)]
        ]
        ))

        return builder.as_markup(
            resize_keyboard=True,
            # one_time_keyboard=True,
            input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item)

    @staticmethod
    def generate_switches_kb(switches: ConfigurationSwitches, ctx: Context) -> types.ReplyKeyboardMarkup:
        builder = ReplyKeyboardBuilder()

        for switch in switches.switches:
            label = switch.name.get(ctx.lang)
            builder.add(types.KeyboardButton(text=f"{label} ✅"
                                            if switch.enabled
                                            else label))
        builder.adjust(3)

        builder.attach(ReplyKeyboardBuilder([
            [types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back)]
        ]
        ))

        return builder.as_markup(
            resize_keyboard=True,
            # one_time_keyboard=True,
            input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item)

    @staticmethod
    def generate_additionals_kb(available_additionals: list[ProductAdditional], additionals: list[ProductAdditional], ctx: Context):
        builder = ReplyKeyboardBuilder()

        for additional in available_additionals:
            label = additional.name.get(ctx.lang)
            builder.add(types.KeyboardButton(text=f"{label} ✅"
                                            if additional in additionals
                                            else label))

        builder.attach(ReplyKeyboardBuilder([
            [types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back)]
        ]
        ))

        return builder.as_markup(
            resize_keyboard=True,
            # one_time_keyboard=True,
            input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item)

class CartKBs:
    @staticmethod
    async def cart_view(entry: CartEntry, current: int, amount: int, total_price: LocalizedMoney, ctx: Context) -> types.ReplyKeyboardMarkup:
        controls = [
            types.KeyboardButton(text="⬅️"),
            types.KeyboardButton(text=f"{current}/{amount}"),
            types.KeyboardButton(text="➡️")
        ] if amount > 1 else [
            types.KeyboardButton(text=f"{current}/{amount}")
        ]
        
        requires_price_confirmation = await ctx.db.cart_entries.check_price_confirmation_in_cart(ctx.customer)
        
        kb = [
            [
                types.KeyboardButton(text='❌'),
                types.KeyboardButton(text="➖"),
                types.KeyboardButton(text=f"{entry.quantity} {ctx.t.UncategorizedTranslates.unit(entry.quantity)}"),
                types.KeyboardButton(text="➕")
            ],
            controls,
            [
                types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back),
                types.KeyboardButton(text=ctx.t.ReplyButtonsTranslates.Cart.send_to_check if requires_price_confirmation else ctx.t.ReplyButtonsTranslates.Cart.place.format(price=total_price.to_text(ctx.customer.currency)))
            ]
        ]

        return types.ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True,
            input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item
        )
    
    @staticmethod
    def cart_price_confirmation(ctx: Context) -> types.ReplyKeyboardMarkup:
        return types.ReplyKeyboardMarkup(
            keyboard=[
                [
                    types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back),
                    types.KeyboardButton(text=ctx.t.ReplyButtonsTranslates.Cart.send)
                ]
            ],
            resize_keyboard=True,
            input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item
        )
    
    @staticmethod
    def cart_order_configuration(order: Order, ctx: Context) -> types.ReplyKeyboardMarkup:
        use_promocode = ctx.t.ReplyButtonsTranslates.Cart.OrderConfiguration.use_promocode
        use_bonus_money = ctx.t.ReplyButtonsTranslates.Cart.OrderConfiguration.use_bonus_money
        proceed_to_payment = ctx.t.ReplyButtonsTranslates.Cart.OrderConfiguration.proceed_to_payment
        change_payment_method = ctx.t.ReplyButtonsTranslates.Cart.OrderConfiguration.change_payment_method
        choose_payment_method = ctx.t.ReplyButtonsTranslates.Cart.OrderConfiguration.choose_payment_method

        used_bonus_money = bool(order.price_details.bonuses_applied)
        
        has_bonus_money = ctx.customer.bonus_wallet.amount > 0.0
        
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
                types.KeyboardButton(text=change_payment_method if order.payment_method else choose_payment_method)
            ],
            [
                types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back),
                types.KeyboardButton(text=proceed_to_payment)
            ]
        ]

        return types.ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True,
            input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item
        )

    @staticmethod
    def payment_method_choose(order: Order, ctx: Context) -> types.ReplyKeyboardMarkup:
        builder = ReplyKeyboardBuilder()
        
        for key, method in SUPPORTED_PAYMENT_METHODS.get_enabled(ctx.customer.currency).items():
            name = f"{method.name.get(ctx.lang)} ✅" if key == order.payment_method_key else method.name.get(ctx.lang)
            builder.add(types.KeyboardButton(text=name))

        builder.adjust(2)
        builder.attach(ReplyKeyboardBuilder([[types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back)]]))
        return builder.as_markup(
            resize_keyboard=True,
            input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item
        )
        
    @staticmethod
    def payment_confirmation(order: Order, ctx: Context) -> types.ReplyKeyboardMarkup:
        
        if order.payment_method and order.payment_method.manual:
            kb = [
                [
                    types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back),
                    types.KeyboardButton(text=ctx.t.ReplyButtonsTranslates.Cart.OrderConfiguration.i_paid)
                ]
            ]

            return types.ReplyKeyboardMarkup(
                keyboard=kb,
                resize_keyboard=True,
                input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item
            )
        else:
            return
        
class OrdersKBs:
    @staticmethod
    def order_view(order: Order, ctx: Context) -> types.ReplyKeyboardMarkup:
        kb = [
            [
                types.KeyboardButton(text=ReplyButtonsTranslates.Orders.Infos.any_question)
            ] if order.state == OrderStateKey.waiting_for_manual_payment_confirm else None,
            [
                types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back)
            ]
            
        ]
        
        kb.remove(None)
        return types.ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True,
            input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item
        )
           
class ProfileKBs:
    
    @staticmethod
    def menu(ctx: Context) -> types.ReplyKeyboardMarkup:
        kb = [
            [
                types.KeyboardButton(text=ctx.t.ReplyButtonsTranslates.Profile.settings)
            ],
            [
                types.KeyboardButton(text=ctx.t.ReplyButtonsTranslates.Profile.referrals),
                types.KeyboardButton(text=ctx.t.ReplyButtonsTranslates.Profile.delivery)
            ],
            [
                types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back)
            ]
            
        ]
        return types.ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True,
            input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item
        )
    
    class Settings:
    
        @staticmethod
        def menu(ctx: Context) -> types.ReplyKeyboardMarkup:
            kb = [
                [
                    types.KeyboardButton(text=ctx.t.ReplyButtonsTranslates.Profile.Settings.lang),
                    types.KeyboardButton(text=ctx.t.ReplyButtonsTranslates.Profile.Settings.currency)
                ],
                [
                    types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back)
                ]
                
            ]
            return types.ReplyKeyboardMarkup(
                keyboard=kb,
                resize_keyboard=True,
                input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item
            )
        
        @staticmethod
        def lang_choose(ctx: Context) -> types.ReplyKeyboardMarkup:
            builder = ReplyKeyboardBuilder()
            for key in SUPPORTED_LANGUAGES_TEXT.keys():

                builder.add(types.KeyboardButton(text=key))

            builder.adjust(2)
            builder.attach(ReplyKeyboardBuilder([[types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back)]]))
            return builder.as_markup(
                resize_keyboard=True,
                input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item)
        
        @staticmethod
        def currency_choose(ctx: Context) -> types.ReplyKeyboardMarkup:
            builder = ReplyKeyboardBuilder()
            for key in SUPPORTED_CURRENCIES.keys():

                builder.add(types.KeyboardButton(text=getattr(ctx.t.UncategorizedTranslates.Currencies, key)))

            builder.adjust(2)
            builder.attach(ReplyKeyboardBuilder([[types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back)]]))
            return builder.as_markup(
                resize_keyboard=True,
                input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item)
    
    class Delivery:
        
        @staticmethod
        def menu(delivery_info: Optional[DeliveryInfo], ctx: Context) -> types.ReplyKeyboardMarkup:

            # Клавиатура, если сервис доставки выбран
            if delivery_info:
                # Текст для иностранной доставки
                foreign_text = (
                    ctx.t.ReplyButtonsTranslates.Profile.Delivery.Edit.foreign + (" ✅"
                    if delivery_info.is_foreign else " ❌")
                )
                keyboard = [
                    [
                        types.KeyboardButton(text=foreign_text),
                        types.KeyboardButton(text=delivery_info.service.name.get(ctx.lang))
                    ],
                    [
                        types.KeyboardButton(text=delivery_info.service.selected_option.name.get(ctx.lang)),
                        types.KeyboardButton(text=ctx.t.ReplyButtonsTranslates.Profile.Delivery.Edit.change_data)
                    ],
                    [
                        types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back),
                        types.KeyboardButton(text=ctx.t.ReplyButtonsTranslates.Profile.Delivery.Edit.delete)
                    ]
                ]
            else:
                keyboard = [
                    [
                        types.KeyboardButton(text=ctx.t.ReplyButtonsTranslates.Profile.Delivery.menu_not_set)
                    ],
                    [
                        types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back)
                    ]
                ]

            return types.ReplyKeyboardMarkup(
                keyboard=keyboard,
                resize_keyboard=True,
                input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item
            )
        
        class Editables:
            
            
            @staticmethod
            def is_foreign(first_setup: bool, ctx: Context) -> types.ReplyKeyboardMarkup:
                keyboard = [
                    [
                        types.KeyboardButton(text=ctx.t.ProfileTranslates.Delivery.foreign_choice_rus),
                        types.KeyboardButton(text=ctx.t.ProfileTranslates.Delivery.foreign_choice_foreign)
                    ],
                    [
                        types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back if first_setup else ctx.t.UncategorizedTranslates.cancel)
                    ]
                ]
                return types.ReplyKeyboardMarkup(
                    keyboard=keyboard,
                    resize_keyboard=True,
                    input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item
                )
                
            @staticmethod
            def services(first_setup: bool, services: Iterable[DeliveryService], ctx: Context) -> types.ReplyKeyboardMarkup:
                builder = ReplyKeyboardBuilder()
            
                for service in services:
                    builder.add(types.KeyboardButton(text=f"{service.name.get(ctx.lang)} ({service.price.to_text(ctx.customer.currency)})"))

                builder.adjust(2)
                
                
                keyboard = [
                    [
                        types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back if first_setup else ctx.t.UncategorizedTranslates.cancel)
                    ]
                ]
                builder.attach(ReplyKeyboardBuilder(keyboard))
                
                return types.ReplyKeyboardMarkup(
                    keyboard=builder.export(),
                    resize_keyboard=True,
                    input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item
                )
            
            @staticmethod
            def requirements_lists(first_setup: bool, lists: list[DeliveryRequirementsList], ctx: Context) -> types.ReplyKeyboardMarkup:
                builder = ReplyKeyboardBuilder()
            
                for lst in lists:
                    builder.add(types.KeyboardButton(text=lst.name.get(ctx.lang)))

                builder.adjust(2)
                
                
                keyboard = [
                    [
                        types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back if first_setup else ctx.t.UncategorizedTranslates.cancel)
                    ]
                ]
                builder.attach(ReplyKeyboardBuilder(keyboard))
                
                return types.ReplyKeyboardMarkup(
                    keyboard=builder.export(),
                    resize_keyboard=True,
                    input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item
                )
            
            @staticmethod
            def requirement(first_setup: bool, ctx: Context) -> types.ReplyKeyboardMarkup:
                keyboard = [
                    [
                        types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back if first_setup else ctx.t.UncategorizedTranslates.cancel)
                    ]
                ]
                
                return types.ReplyKeyboardMarkup(
                    keyboard=keyboard,
                    resize_keyboard=True,
                    input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item
                )
        
        
    
    class Balance:
            
        @staticmethod
        def change_currency(current_currency: str, ctx: Context) -> types.ReplyKeyboardMarkup:
            builder = ReplyKeyboardBuilder()
            for currency in [cur for cur in SUPPORTED_CURRENCIES.keys() if cur != current_currency]:
                builder.add(types.KeyboardButton(text=currency))

            builder.adjust(2)
            
            markup = types.ReplyKeyboardMarkup(keyboard=
                                            [[
                                                types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back)
                                            ]]
                                        )
            builder.attach(ReplyKeyboardBuilder.from_markup(markup))
            
            return builder.as_markup(
                resize_keyboard=True,
                #one_time_keyboard=True,
                input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item)
    
class UncategorizedKBs:
    @staticmethod
    def inline_back(ctx: Context) -> types.InlineKeyboardMarkup:
        kb = [
            [
                types.InlineKeyboardButton(text=ctx.t.UncategorizedTranslates.back, callback_data="back")
            ]
        ]
        return types.InlineKeyboardMarkup(
            inline_keyboard=kb
        )
        
    @staticmethod
    def reply_back(ctx: Context) -> types.ReplyKeyboardMarkup:
        kb = [
            [
                types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back)
            ]
        ]
        return types.ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True,
            input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item
        )

    @staticmethod
    def inline_cancel(ctx: Context) -> types.InlineKeyboardMarkup:
        kb = [
            [
                types.InlineKeyboardButton(text=ctx.t.UncategorizedTranslates.cancel, callback_data="cancel")
            ]
        ]
        return types.InlineKeyboardMarkup(
            inline_keyboard=kb
        )
    
    @staticmethod
    def yes_no(ctx: Context) -> types.ReplyKeyboardMarkup:
        kb = [
            [
                types.KeyboardButton(text=ctx.t.UncategorizedTranslates.no),
                types.KeyboardButton(text=ctx.t.UncategorizedTranslates.yes)
            ]
        ]
        
        return types.ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True,
            input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item
        )

