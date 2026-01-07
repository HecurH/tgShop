from typing import Iterable, Optional
from aiogram import types
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

from registry.currencies import SUPPORTED_CURRENCIES
from registry.payments import SUPPORTED_PAYMENT_METHODS
from core.helper_classes import Context
from schemas.db_models import *
from core.types.enums import CartItemSource, OrderStateKey
from core.types.values import LocalizedMoney
from ui.message_tools import strike

from configs.languages import SUPPORTED_LANGUAGES_TEXT
from ui.translates import EnumTranslates, ReplyButtonsTranslates, UncategorizedTranslates

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
                types.KeyboardButton(text=ctx.t.ReplyButtonsTranslates.discounted_products),
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
    
    @staticmethod
    def admin_menu() -> types.ReplyKeyboardMarkup:
        kb = [
            [
                types.KeyboardButton(text="Покупатели"),
                types.KeyboardButton(text="Уценка"),
                types.KeyboardButton(text="Товары")
            ],
            [
                types.KeyboardButton(text="Заказы"),
                types.KeyboardButton(text="Промокоды")
            ],
            [
                types.KeyboardButton(text="Глобальные Плейсхолдеры")
            ]
        ]
        return types.ReplyKeyboardMarkup(keyboard=kb, 
                                         resize_keyboard=True)
    
    class Customers:
        @staticmethod
        def customer_menu(customer: Customer, ctx: Context) -> types.ReplyKeyboardMarkup:
            kb = [
                [
                    types.KeyboardButton(text="Написать сообщение")
                ],
                [
                    types.KeyboardButton(text="Разблокировать" if customer.banned else "Заблокировать")
                ],
                [
                    types.KeyboardButton(text="История сообщений")
                ],
                [
                    types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back)
                ]
            ]
            return types.ReplyKeyboardMarkup(keyboard=kb, 
                                         resize_keyboard=True)
        
    
    class Promocodes:
        @staticmethod
        def admin_promocodes_menu(ctx: Context) -> types.ReplyKeyboardMarkup:
            kb = [
                [
                    types.KeyboardButton(text="Создать"),
                    types.KeyboardButton(text="Список всех")
                ],
                [
                    types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back)
                ]
            ]
            return types.ReplyKeyboardMarkup(keyboard=kb,
                                             resize_keyboard=True)
    
    class GlobalPlaceholders:
        @staticmethod
        def admin_global_placeholders_menu(ctx: Context) -> types.ReplyKeyboardMarkup:
            kb = [
                [
                    types.KeyboardButton(text="Создать"),
                    types.KeyboardButton(text="Список всех")
                ],
                [
                    types.KeyboardButton(text="Изменить")
                ],
                [
                    types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back)
                ]
            ]
            return types.ReplyKeyboardMarkup(keyboard=kb,
                                             resize_keyboard=True)
    
    class DiscountedProducts:
        @staticmethod
        def admin_discounted_products_menu(ctx: Context) -> types.ReplyKeyboardMarkup:
            kb = [
                [
                    types.KeyboardButton(text="Создать"),
                    types.KeyboardButton(text="Список всех")
                ],
                [
                    types.KeyboardButton(text="Удалить")
                ],
                [
                    types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back)
                ]
            ]
            
            return types.ReplyKeyboardMarkup(keyboard=kb,
                                             resize_keyboard=True)
    
    class Orders:
        @staticmethod
        def orders_menu(ctx: Context) -> types.ReplyKeyboardMarkup:
            kb = [
                [
                    types.KeyboardButton(text=ctx.t.UncategorizedTranslates.cancel)
                ]
            ]
            return types.ReplyKeyboardMarkup(keyboard=kb,
                                            resize_keyboard=True)
        
        @staticmethod
        def order_menu(ctx: Context) -> types.ReplyKeyboardMarkup:
            kb = [
                [
                    types.KeyboardButton(text="Изменить статус"),
                    types.KeyboardButton(text="Посмотреть историю комментариев")
                ],
                [
                    types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back)
                ]
            ]
            return types.ReplyKeyboardMarkup(keyboard=kb,
                                            resize_keyboard=True)
        
        @staticmethod
        def change_status_choice(ctx: Context) -> types.ReplyKeyboardMarkup:
            kb = []
            for state in OrderStateKey:
                kb.append([types.KeyboardButton(text=EnumTranslates.OrderStateKey.translate(state.value, ctx.lang))])
            kb.append([types.KeyboardButton(text=ctx.t.UncategorizedTranslates.cancel)])
            return types.ReplyKeyboardMarkup(keyboard=kb,
                                             resize_keyboard=True)
            
class AssortmentKBs:

    @staticmethod
    def assortment_menu(categories: Iterable[Category], ctx: Context) -> types.ReplyKeyboardMarkup:
        builder = ReplyKeyboardBuilder()
        for category in categories:

            builder.add(types.KeyboardButton(text=category.localized_name.get(ctx)))

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
                    text=option.name.get(ctx)
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
                    text=ctx.t.ReplyButtonsTranslates.Assortment.extra_options
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
        main_builder = ReplyKeyboardBuilder()
        
        choices: list[ConfigurationChoice] = []
        switches: list[ConfigurationSwitches] = []
        annotations: list[ConfigurationAnnotation] = []
        for choice in option.choices.values():
            if isinstance(choice, ConfigurationChoice): choices.append(choice)
            elif isinstance(choice, ConfigurationSwitches): switches.append(choice)
            elif isinstance(choice, ConfigurationAnnotation): annotations.append(choice)
            
        for choice in choices:
            price_text = f" {choice.price.to_text(ctx.customer.currency)}" if choice.price.get_amount(ctx.customer.currency) != 0 else ""

            is_blocked = choice.check_blocked_all(product.configuration.options)

            name = f"{strike(choice.name.get(ctx) + price_text)} 🔒" if is_blocked else f"{choice.name.get(ctx)}{price_text}"
            main_builder.add(types.KeyboardButton(text=f">{name}<"
                                            if option.get_chosen().name == choice.name
                                            else name))
        main_builder.adjust(3)
        
        second_builder = ReplyKeyboardBuilder()
        for switch in switches:
            second_builder.add(types.KeyboardButton(text=switch.name.get(ctx)))
        
        for ann in annotations:
            second_builder.add(types.KeyboardButton(text=ann.name.get(ctx)))
            
        second_builder.adjust(2)
        main_builder.attach(second_builder)

        main_builder.attach(ReplyKeyboardBuilder([
            [types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back)]
        ]
        ))

        return main_builder.as_markup(
            resize_keyboard=True,
            # one_time_keyboard=True,
            input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item)

    @staticmethod
    def generate_switches_kb(configuration: ProductConfiguration, switches: ConfigurationSwitches, ctx: Context) -> types.ReplyKeyboardMarkup:
        builder = ReplyKeyboardBuilder()
        def gen_name(switch: ConfigurationSwitch):
            blocked = switch.check_blocked_all(configuration.options)
            is_blocked = "🔒" if blocked else ""
            is_enabled = "✅" if switch.enabled else ""
            name = strike(switch.name.get(ctx)) if blocked else switch.name.get(ctx)
            
            return f"{name} {is_enabled}{is_blocked}".strip()
        
        current_row = []
        
        for switch_or_group in switches.get_all():
            if isinstance(switch_or_group, ConfigurationSwitch):
                current_row.append(types.KeyboardButton(text=gen_name(switch_or_group)))
                if len(current_row) == 3:
                    builder.row(*current_row)
                    current_row = []
            elif isinstance(switch_or_group, ConfigurationSwitchesGroup):
                if current_row:
                    builder.row(*current_row)
                    current_row = []
                
                builder.row(types.KeyboardButton(text=f"-- {switch_or_group.name.get(ctx)} --"))
                for switch in switch_or_group.get_all():
                    current_row.append(types.KeyboardButton(text=gen_name(switch)))
                    if len(current_row) == 3:
                        builder.row(*current_row)
                        current_row = []
        
        if current_row:
            builder.row(*current_row)
        
        builder.row(types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back))
        
        return builder.as_markup(
            resize_keyboard=True,
            input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item)

    @staticmethod
    def generate_additionals_kb(available_additionals: list[ProductAdditional], additionals: list[ProductAdditional], ctx: Context):
        builder = ReplyKeyboardBuilder()

        for additional in available_additionals:
            name = additional.name.get(ctx)
            builder.add(types.KeyboardButton(text=f"{name} ✅"
                                            if additional in additionals
                                            else name))

        builder.attach(ReplyKeyboardBuilder([
            [types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back)]
        ]
        ))

        return builder.as_markup(
            resize_keyboard=True,
            # one_time_keyboard=True,
            input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item)

class DiscountedProductKBs:
    
    @staticmethod
    def gen_discounted_product_view(current: int, amount: int, ctx: Context) -> types.ReplyKeyboardMarkup:
        controls = [
            types.KeyboardButton(text="⬅️"),
            types.KeyboardButton(text=f"{current}/{amount}"),
            types.KeyboardButton(text="➡️")
        ] if amount > 1 else [
            types.KeyboardButton(text=f"{current}/{amount}")
        ]
        
        kb = [
            [
                types.KeyboardButton(text=ctx.t.ReplyButtonsTranslates.DiscountedProducts.add_to_cart)
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
        
        requires_price_confirmation = await ctx.services.db.cart_entries.check_price_confirmation_in_cart(ctx.customer)
        is_product = entry.source_type == CartItemSource.product
        
        kb = [
            [
                types.KeyboardButton(text='❌'),
                types.KeyboardButton(text="➖" if is_product else "🔒"),
                types.KeyboardButton(text=f"{entry.quantity} {ctx.t.UncategorizedTranslates.unit(entry.quantity)}"),
                types.KeyboardButton(text="➕" if is_product else "🔒")
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
            name = f"{method.name.get(ctx)} ✅" if key == order.payment_method_key else method.name.get(ctx)
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
        kb = []
        
        if order.state == OrderStateKey.waiting_for_manual_payment_confirm:
            kb.append([types.KeyboardButton(text=ctx.t.ReplyButtonsTranslates.Orders.Infos.any_question)])
            
        if order.state == OrderStateKey.waiting_for_forming:
            kb.append([types.KeyboardButton(text=ctx.t.ReplyButtonsTranslates.Orders.continue_forming)])
            
        if order.state.comment:
            kb.append([types.KeyboardButton(text=ctx.t.ReplyButtonsTranslates.Orders.view_comment if len(order.state.comment) == 1 else ctx.t.ReplyButtonsTranslates.Orders.view_comments)])
        
        kb.append([types.KeyboardButton(text=ctx.t.UncategorizedTranslates.back)])
        
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
                    types.KeyboardButton(text=ReplyButtonsTranslates.Profile.Settings.lang.translate(ctx.lang)),
                    types.KeyboardButton(text=ReplyButtonsTranslates.Profile.Settings.currency.translate(ctx.lang))
                ],
                [
                    types.KeyboardButton(text=UncategorizedTranslates.back.translate(ctx.lang))
                ]
                
            ]
            #.translate(ctx.lang) тк ctx.t не обновляется сам
            return types.ReplyKeyboardMarkup(
                keyboard=kb,
                resize_keyboard=True,
                input_field_placeholder=ReplyButtonsTranslates.choose_an_item.translate(ctx.lang)
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
    
    class Referrals:
        @staticmethod
        def ask_for_join(ctx: Context):
            kb = [
                [
                    types.KeyboardButton(text=ctx.t.UncategorizedTranslates.yes),
                    types.KeyboardButton(text=ctx.t.UncategorizedTranslates.what_is_this)
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
        def menu(ctx: Context) -> types.ReplyKeyboardMarkup:
            kb = [
                [
                    types.KeyboardButton(text=ctx.t.ReplyButtonsTranslates.Profile.Referrals.invitation_link)
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
    
    class Delivery:
        
        @staticmethod
        def menu(delivery_info: Optional[DeliveryInfo], ctx: Context) -> types.ReplyKeyboardMarkup:

            # Клавиатура, если сервис доставки выбран
            if delivery_info:
                # Текст для иностранной доставки
                foreign_text = (
                    ctx.t.ReplyButtonsTranslates.Profile.Delivery.Edit.foreign + (" ✅"
                    if delivery_info.service.is_foreign else " ❌")
                )
                keyboard = [
                    [
                        types.KeyboardButton(text=foreign_text),
                        types.KeyboardButton(text=delivery_info.service.name.get(ctx))
                    ],
                    [
                        types.KeyboardButton(text=delivery_info.service.selected_option.name.get(ctx)),
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
                    price_text = "" if service.requires_manual_confirmation else f" ({service.price.to_text(ctx.customer.currency)})"
                    builder.add(types.KeyboardButton(text=f"{service.name.get(ctx)}{price_text}"))

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
                    builder.add(types.KeyboardButton(text=lst.name.get(ctx)))

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
    def reply_cancel(ctx: Context) -> types.ReplyKeyboardMarkup:
        kb = [
            [
                types.KeyboardButton(text=ctx.t.UncategorizedTranslates.cancel)
            ]
        ]
        return types.ReplyKeyboardMarkup(
            keyboard=kb,
            resize_keyboard=True,
            input_field_placeholder=ctx.t.ReplyButtonsTranslates.choose_an_item
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
        
    @staticmethod
    def inline_yes_no(ctx: Context) -> types.InlineKeyboardMarkup:
        kb = [
            [
                types.InlineKeyboardButton(text=ctx.t.UncategorizedTranslates.no, callback_data="no"),
                types.InlineKeyboardButton(text=ctx.t.UncategorizedTranslates.yes, callback_data="yes")
            ]
        ]

        return types.InlineKeyboardMarkup(
            inline_keyboard=kb
        )
        
    

    @staticmethod
    async def go_to_bot(ctx: Context) -> types.InlineKeyboardMarkup:
        me = await ctx.message.bot.get_me()
        keyboard = [
            [
                types.InlineKeyboardButton(text="Перейти к боту",
                                            url=f"tg://resolve?domain={me.username}")
            ]
        ]
        return types.InlineKeyboardMarkup(inline_keyboard=keyboard)
