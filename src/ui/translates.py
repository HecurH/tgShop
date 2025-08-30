import logging
from types import SimpleNamespace
from typing import ClassVar, Type

from configs.supported import SUPPORTED_LANGUAGES_TEXT

class TranslationField:
    """
    Дескриптор, который возвращает перевод в зависимости от языка экземпляра.
    """

    def __init__(self, translations: dict):
        self.translations = translations
        self._attribute_name = None  # имя будет установлено метаклассом
        self._owner_class = None

    def __set_name__(self, owner, name):
        # сохраняет имя атрибута, к которому привязан дескриптор
        if self._attribute_name is not None:
            raise RuntimeError(
                f"TranslationField instance already assigned to attribute '{self._attribute_name}'. "
                f"Do not reuse the same TranslationField instance for multiple attributes/classes."
            )
        self._attribute_name = name
        self._owner_class = owner

    def __get__(self, instance, owner):
        # instance - это экземпляр класса, owner - это сам класс
        if instance is None:
            # если обращаемся к атрибуту через класс, возвращаем сам дескриптор
            return self

        lang = instance._lang
        
        value = (
            self.translations.get(lang)
            or self.translations.get('en')
            or next(iter(self.translations.values()))
        )

        if isinstance(value, dict):
            def pluralizer(count: int):
                return owner.translate(self._attribute_name, lang, count=count)
            return pluralizer
        else:
            return owner.translate(self._attribute_name, lang)
    
    def translate(self, lang: str, count: int = None) -> str:
        if self._owner_class is None:
            raise RuntimeError("TranslationField has no owner_class yet")

        return self._owner_class.translate(self._attribute_name, lang, count=count)
    
    def values(self):
        return self.translations.values()
        
        
class TranslationMeta(type):
    """Метакласс для автоматической организации переводов"""

    def __new__(cls, name, bases, attrs):
        translations = {}
        reverse_translations = {}

        for base in bases:
            if hasattr(base, '_translations'):
                translations |= base._translations
            if hasattr(base, '_reverse_translations'):
                for lang, texts in base._reverse_translations.items():
                    reverse_translations.setdefault(lang, {}).update(texts)

        for attr_name, value in attrs.items():
            if isinstance(value, dict) and all(isinstance(k, str) for k in value.keys()):
                translations[attr_name] = value
                for lang, text in value.items():
                    # для плюрализации не создаем обратный словарь
                    if isinstance(text, str):
                        reverse_translations.setdefault(lang, {})[text] = attr_name

                attrs[attr_name] = TranslationField(value)

        attrs['_translations'] = translations
        attrs['_reverse_translations'] = reverse_translations

        new_class = super().__new__(cls, name, bases, attrs)

        if name != 'Translatable' and issubclass(new_class, Translatable):
            TranslatorHub.register(new_class)
            
        return new_class

class Translatable(metaclass=TranslationMeta):
    """Базовый класс для переводимых объектов"""
    
    def __init__(self, lang: str):
        self._lang = lang

    @staticmethod
    def _get_plural_form(lang: str, count: int) -> str:
        # sourcery skip: remove-unnecessary-else, swap-if-else-branches
        if lang == "ru":
            if count % 10 == 1 and count % 100 != 11: return "one"
            elif 2 <= count % 10 <= 4 and (count % 100 < 10 or count % 100 >= 20): return "few"
            else: return "many"
        else: return "one" if count == 1 else "other"

    @classmethod
    def translate(cls, attribute: str, lang: str, default_lang: str = 'en', count: int = None) -> str:
        logger = logging.getLogger(__name__)
        translations = cls._translations.get(attribute, {})

        value = translations.get(lang) or translations.get(default_lang)
        if value is None:
            if translations:
                fallback_lang, value = next(iter(translations.items()))
                logger.warning(f"No '{lang}' or '{default_lang}' translation for '{attribute}', falling back to '{fallback_lang}'.")
            else:
                logger.warning(f"No translations found for '{attribute}'.")
                return "<untranslated>"

        if isinstance(value, str) or count is None:
            return value
        form = cls._get_plural_form(lang, count)
        if form not in value:
            available_forms = ", ".join(value.keys())
            logger.warning(
                f"Plural form '{form}' not found for '{attribute}' in '{lang}'. "
                f"Available forms: {available_forms}. "
                f"Please update translations to include this plural form."
            )
            # возвращаем плейсхолдер, чтобы было видно в ui
            return f"<missing plural '{form}' for '{attribute}' in '{lang}'>"

        return value[form]

    
    @classmethod
    def get_attribute(cls, text, lang: str) -> str:
        """Получить имя атрибута по переводу"""
        return cls._reverse_translations.get(lang, {}).get(str(text))
    
    @classmethod
    def get_all_attributes(cls, lang: str) -> list:
        """Получить имена всех атрибутов класса по переводу"""
        return list(cls._reverse_translations.get(lang, {}).keys())

    @classmethod
    def supported_languages(cls) -> set:
        """Получить все поддерживаемые языки"""
        return {
            lang
            for trans in cls._translations.values()
            for lang in trans.keys()
        }

class TranslatorNamespace(SimpleNamespace):
    def __repr__(self):
        return f"<TranslatorNamespace {list(self.__dict__.keys())}>"

class TranslatorHub:
    _cache: ClassVar[dict[str, "TranslatorHub"]] = {}
    _registered_classes: ClassVar[list[Type[Translatable]]] = []

    def __init__(self, lang: str):
        self._lang = lang

        # обрабатываем классы по глубине __qualname__ — родители первыми
        classes_sorted = sorted(
            self._registered_classes,
            key=lambda c: len(c.__qualname__.split('.'))
        )

        for cls in classes_sorted:
            parts = cls.__qualname__.split('.')   # например, ['UncategorizedTranslates','Currencies']
            parent = self

            # пробегаем по промежуточным частям пути и находим или создаём контейнер
            for part in parts[:-1]:
                if hasattr(parent, part):
                    parent = getattr(parent, part)
                else:
                    ns = TranslatorNamespace()
                    setattr(parent, part, ns)
                    parent = ns

            final_name = cls.__name__  # реальное имя класса, PascalCase
            # создаём экземпляр переводчика (с lang) и присваиваем к найденному parent
            instance = cls(lang=lang)
            setattr(parent, final_name, instance)

    @classmethod
    def register(cls, translatable_class: Type[Translatable]):
        if translatable_class not in cls._registered_classes:
            cls._registered_classes.append(translatable_class)

    @classmethod
    def get_for_lang(cls, lang: str) -> "TranslatorHub":
        if lang not in cls._cache:
            if lang not in SUPPORTED_LANGUAGES_TEXT.values():
                logging.getLogger(__name__).warning(f"Can't get TranslatorHub for {lang} language.")
                return cls.get_for_lang('en')
            cls._cache[lang] = TranslatorHub(lang=lang)
        return cls._cache[lang]
    
class EnumTranslates(Translatable):
    
    class PromocodeCheckResult(Translatable):
        only_newbies = {
            "ru": "Этот промокод можно использовать только при первом заказе!",
            "en": "This promo code can only be used on your first order!"
        }
        
        max_usages_reached = {
            "ru": "Данный промокод уже использован максимальное количество раз.",
            "en": "This promo code has been used the maximum number of times."
        }
        
        expired = {
            "ru": "Истёк срок действия промокода.",
            "en": "The promo code has expired."
        }
        
        error = {
            "ru": "Данный промокод не может быть применён.",
            "en": "This promo code cannot be applied."
        }
        
        
    
    class OrderStateKey(Translatable):
        forming = {
            "ru": "Формирование заказа",
            "en": "Order forming"
        }

        waiting_for_payment = {
            "ru": "Ожидает оплаты",
            "en": "Waiting for payment"
        }

        waiting_for_manual_payment_confirm = {
            "ru": "Ожидает подтверждения оплаты",
            "en": "Waiting for payment confirmation"
        }
        
        waiting_for_price_confirmation = {
            "ru": "Ожидает подтверждения цены",
            "en": "Waiting for price confirmation"
        }
        
        assembled_waiting_for_send = {
            "ru": "Собран, ожидает отправки",
            "en": "Assembled, waiting to be shipped"
        }

        sent = {
            "ru": "Отправлен",
            "en": "Sent"
        }

        received = {
            "ru": "Получен",
            "en": "Received"
        }

class UncategorizedTranslates(Translatable):
    oopsie = {
        "ru": "Упс! Прости, мне нужно начать заново...",
        "en": "Oops! I'm sorry, I need to start over..."
    }
    
    ok_dont_changing = {
        "ru": "Окей, оставим как есть 👌",
        "en": "Okay, let's leave it as is 👌"
    }

    back = {
        "ru": "Назад",
        "en": "Back"
    }

    finish = {
        "ru": "Закончить",
        "en": "Finish"
    }

    cancel = {
        "ru": "Отмена",
        "en": "Cancel"
    }
    
    yes = {
        "ru": "Да",
        "en": "Yes"
    }
    
    no = {
        "ru": "Нет",
        "en": "No"
    }
    
    unit = {
        "ru": {"one": "Шт.", "few": "Шт.", "other": "Шт."} ,
        "en": {"one": "Pc.", "other": "Pcs."}  
    }
    
    class Currencies(Translatable):
        RUB = {
            "ru": "Рубль",
            "en": "Ruble"
        }
        
        USD = {
            "ru": "Доллар",
            "en": "Dollar"
        }

class CommonTranslates(Translatable):
    hi = {
        "ru": "Привет!",
        "en": "Hi!"
    }
    
    currency_choosing = {
        "ru": "Выберите валюту (можно изменить в настройках):",
        "en": "Select a currency (you can change it in the settings):"
    }

    heres_the_menu = {
        "ru": "Вот меню:",
        "en": "Here's the menu:"
    }

class AssortmentTranslates(Translatable):

    choose_the_category = {
        "ru": "Выберите категорию товара:",
        "en": "Select a product category:"
    }

    choose_the_preset = {
        "ru": "Выберите номер готового пресета:",
        "en": "Select the preset number:"
    }

    enter_custom = {
        "ru": "Введите текст-описание:",
        "en": "Enter a text description:"
    }

    switches_enter = {
        "ru": "Переключайте опции кнопками ниже:",
        "en": "Switch the options using the buttons below:"
    }

    no_products_in_category = {
        "ru": "Простите! Судя по всему, товаров данной категории не существует.",
        "en": "Sorry! Apparently, there are no products in this category."
    }

    total = {
        "ru": "💵 Итоговая стоимость: ",
        "en": "💵 Total: "
    }

    additionals = {
        "ru": "Другое",
        "en": "Other"
    }
    
    cannot_choose = {
        "ru": "Эта опция недоступна, пока вы выбрали {path}.",
        "en": "This option is unavailable while you have selected {path}."
    }

    cannot_price = {
        "ru": "Определить точную цену товара невозможно.",
        "en": "It is impossible to determine the exact price of the product."
    }

    approximate_price = {
        "ru": "💵 Приблизительная цена: ",
        "en": "💵 Approximate price: "
    }

    currently_selected = {
        "ru": "На данный момент выбраны такие настройки:",
        "en": "The following settings are currently selected: "
    }

    add_to_cart_finished = {
        "ru": "Товар успешно добавлен в корзину!",
        "en": "The product has been successfully added to the cart!"
    }
    
class CartTranslates(Translatable):
    no_products_in_cart = {
        "ru": "В вашей корзине нет товаров!",
        "en": "There are no products in your cart!"
    }
    
    cart_view_menu = {
        "ru": "{name} — {price}\n\n{configuration}",
        "en": "{name} — {price}\n\n{configuration}"
    }
    
    entry_remove_confirm = {
        "ru": "Вы действительно хотите удалить этот товар из корзины?",
        "en": "Are you sure you want to remove this item from the cart?"
    }
    
    delivery_not_configured = {
        "ru": "Перед оформлением заказа необходимо настроить доставку.",
        "en": "Before placing an order, you need to set up delivery."
    }
        
    cart_price_confirmation = {
        "ru": "В вашей корзине есть товары с индивидуальными параметрами, поэтому мы рассчитаем итоговую цену вручную.\n\nОтправьте заказ на подтверждение, и мы пришлем уведомление, как только все будет готово. После этого можно будет перейти к оплате.\n\nБазовая стоимость: {price}",
        "en": "There are products with individual parameters in your cart, so we will calculate the total price manually.\n\nSend the order for confirmation, and we will send a notification as soon as everything is ready. After that, you can proceed to payment.\n\nBase price: {price}"
    }
    
    price_confirmation_sent = {
        "ru": "Корзина отправлена на подтверждение!",
        "en": "The cart has been sent for confirmation!"
    }
    
    class OrderConfiguration(Translatable):
    
        order_configuration_menu = {
            "ru": """<b>🛒 ДЕТАЛИ ЗАКАЗА</b>
━━━━━━━━━━━━━━━━━━━━
{cart_entries_description}
━━━━━━━━━━━━━━━━━━━━
🎫 <b>Промокод:</b> {promocode_info}
💎 <b>Оплата бонусами:</b> {bonus_money_info}
💳 <b>Способ оплаты:</b> {payment_method_info}

🚚 <b>Доставка:</b> {delivery_service}
{delivery_requirements_info}

💸 <b>ИТОГО:</b> {total}""",
            "en": """<b>🛒 ORDER DETAILS</b>
━━━━━━━━━━━━━━━━━━━━
{cart_entries_description}
━━━━━━━━━━━━━━━━━━━━
🎫 <b>Promo code:</b> {promocode_info}
💎 <b>Bonus payment:</b> {bonus_money_info}
💳 <b>Payment method:</b> {payment_method_info}

🚚 <b>Delivery:</b> {delivery_service}
{delivery_requirements_info}

💸 <b>TOTAL</b> {total}"""
        }
        
        enter_promocode = {
            "ru": "Введите промокод:",
            "en": "Enter promo code:"
        }
        
        choose_payment_method = {
            "ru": "{methods_info}\n\nВыберите способ оплаты:",
            "en": "{methods_info}\n\nSelect a payment method:"
        }
        
        no_promocode_applied = {
            "ru": "Не применён.",
            "en": "Not applied."
        }
        
        promocode_not_found = {
            "ru": "Промокод не найден.",
            "en": "Promo code not found."
        }
        
        promocode_check_failed = {
            "ru": "{reason}\n\nПопробуйте другой промокод.",
            "en": "{reason}\n\nTry another promo code."
        }
        
        promocode_applied = {
            "ru": "Промокод применён!",
            "en": "Promo code applied!"
        }
        
        promocode_info = {
            "ru": """{code}; Скидка — {discount}
   Описание: {description}""",
            "en": """{code}; Discount — {discount}
   Description: {description}"""
        }
        
        not_using_bonus_money = {
            "ru": "Не используются.",
            "en": "Not used."
        }
        
        no_bonus_money = {
            "ru": "На данный момент вас нет бонусных денег.\nУзнать подробнее о них вы можете в меню Профиль —> Рефералы.",
            "en": "You have no bonus money at the moment.\nYou can learn more about them in the Profile menu -> Referrals."
        }

        no_payment_method_selected = {
            "ru": "Не выбран. ❗️",
            "en": "Not selected. ❗️"
        }
        
        payment_method_selected = {
            "ru": "Вы выбрали оплату <b>{name}</b>.",
            "en": "You have selected payment <b>{name}</b>."
        }
        
        not_all_required_fields_filled = {
            "ru": "Не все обязательные поля заполнены.",
            "en": "Not all required fields are filled."
        }
        
        payment_confirmation_manual = {
            "ru": """Вы выбрали оплату <b>{payment_method_name}</b>.
Для оплаты используйте реквизиты ниже:
{payment_method_details}

Поскольку это не автоматизируемый метод оплаты, произведенный вами платеж будет проверен вручную. (Вам будет выслано уведомление)
После оплаты заказа нажмите соответствующую кнопку ниже:""",
        }
        
        manual_payment_confirmation_sended = {
            "ru": "Заказ сформирован и ожидает подтверждения оплаты. ✅\nПосле подтверждения бот вышлет вам уведомление. Для дополнительной информации о заказе вы можете перейти в соответствующее меню.",
            "en": "The order has been formed and is awaiting payment confirmation. ✅\nAfter confirmation, the bot will send you a notification. For more information about the order, you can go to the corresponding menu."
        }

class OrdersTranslates(Translatable):
    menu = {
        "ru": "текст над\n\n{orders_info}\n\nвведите номер заказа бла-бла:",
        "en": "text above\n\n{orders_info}\n\nenter order number bla-bla:"
    }
    
    order_viewing_menu = {
        "ru": """<b>Заказ #{order_puid}</b> от {order_forming_date}
{order_entries_description}        

Статус заказа: {order_status}{delivery_info}
Способ оплаты: {payment_method_info}
{promocode_info}{bonus_money_info}

Суммарная стоимость товаров: {products_price}
{price_info}
""",
    }
    
    delivery_info = {
        "ru": "\nДоставка: {info}",
        "en": "\nDelivery: {info}"
    }
    
    promocode_info = {
        "ru": "\nПромокод: {info}",
        "en": "\nPromo code: {info}"
    }

    bonus_money_info = {
        "ru": "\nОплата бонусами: {info}",
        "en": "\nBonus payment: {info}"
    }
    
    waiting_for_price_confirmation_info = {
        "ru": "Ваш заказ ожидает подтверждения цены.",
        "en": "Your order is waiting for price confirmation."
    }
    
    total_price_info = {
        "ru": "Итого: {total_price}",
        "en": "Total: {total_price}"
    }
    
    class Infos(Translatable):
        any_question = {
            "ru": "ну тут ответ на него лол",
            "en": "lol"
        }

class ProfileTranslates(Translatable):
    menu = {
        "ru": "Выберите пункт вашего профиля:",
        "en": "Select an item in your profile:"
    }

    current_bonus_balance = {
        "ru": "На вашем бонусном счету — {balance}.",
        "en": "Your bonus account has {balance}."
    }
    
    current_currency = {
        "ru": "Текущая валюта — {currency}.",
        "en": "The current currency is {currency}."
    }
    
    available_currencies = {
        "ru": "Доступные валюты можете увидеть на кнопках ниже:",
        "en": "You can see the available currencies on the buttons below:"
    }
    
    currency_change_warning = {
        "ru": "Внимание! Конвертировать валюту в следующий раз вы сможете только через неделю!",
        "en": "Conversion will be made at the rate from {fromVal} to {toVal}."
    }

    class Settings(Translatable):
    
        menu = {
            "ru": "Изменяйте настройки кнопками ниже:",
            "en": "Change settings using the buttons below:"
        }
        
        choose_lang = {
            "ru": "Выберите язык:",
            "en": "Choose language:"
        }
        
        choose_currency = {
            "ru": "Ваша текущая валюта — {currency}.\nВыберите валюту:",
            "en": "Your current currency is {currency}.\nSelect a currency:"
        }
        
        lang_changed = {
            "ru": "Вы успешно изменили язык на русский.",
            "en": "You have successfully changed the language to English."
        }
        
        currency_changed = { # currency = [рубль, доллар, ruble, dollar]
            "ru": "Вы успешно изменили валюту на {currency}.",
            "en": "You have successfully changed the currency to {currency}."
        }
        
        nothing_changed = {
            "ru": "Вы успешно ничего не изменили.",
            "en": "You have successfully changed absolutely nothing."
        }
        
    class Delivery(Translatable):
    
        menu = {
            "ru": """Честно, не ебу какой сюда текст вставить, на тут вот инфа о уже настроенной доставке:
  Способ доставки: {delivery_service} ({service_price}), {delivery_req_lists_name}
{requirements}

Изменить информацию о доставке вы можете используя кнопки ниже:""",
            "en": """Честно, не ебу какой сюда текст вставить, на тут вот инфа о уже настроенной доставке:
  Способ доставки: {delivery_service} ({service_price}), {delivery_req_lists_name}
{requirements}

Изменить информацию о доставке вы можете используя кнопки ниже:"""
        }
        
        menu_not_configured = {
            "ru": "Лееее ишак чо не сконфигурировал свою доставку чорт баля, кнопки ниже решат алёу",
            "en": "Лееее ишак чо не сконфигурировал свою доставку чорт баля, кнопки ниже решат алёу"
        }
        
        delete_confimation = {
            "ru": "Вы уверены что хотите удалить данные о доставке?",
            "en": "Are you sure you want to delete your delivery information?"
        }
        
        foreign_choice_rus = {
            "ru": "🇷🇺 Россия",
            "en": "🇷🇺 Russia"
        }
        
        foreign_choice_foreign = {
            "ru": "🌍 За рубеж",
            "en": "🌍 Foreign"
        }
        
        is_foreign_text = { # Россия / За рубеж
            "ru": "Куда будет осуществляться доставка?",
            "en": "Where will the delivery be made?"
        }

        service_text = { # Почта России / Боксберри
            "ru": "Выберите сервис доставки:",
            "en": "Select a delivery service:"
        }

        requirements_list_text = { # По телефону / По ФИО и адресу
            "ru": "Выберите способ оформления доставки:",
            "en": "Select the delivery arrangement method:"
        }

        requirement_value_text = { # Телефон / Адрес; пишите номер в формате +7xxxxxxxxxx
            "ru": "Примечание:\n{description}\n\nВведите <b>{name}</b>:",
            "en": "Note:\n{description}\n\nEnter <b>{name}</b>:"
        }

class ReplyButtonsTranslates(Translatable):
    choose_an_item = {
        "ru": "Выберите пункт...",
        "en": "Select an item..."
    }

    assortment = {
        "ru": "Ассортимент",
        "en": "Assortment"
    }

    cart = {
        "ru": "Корзина",
        "en": "Cart"
    }

    orders = {
        "ru": "Заказы",
        "en": "Orders"
    }

    about = {
        "ru": "О нас",
        "en": "About us"
    }

    profile = {
        "ru": "Профиль",
        "en": "Profile"
    }
    
    class Assortment(Translatable):
        details = {
            "ru": "Подробнее",
            "en": "Details"
        }
        
        add_to_cart = {
            "ru": "Добавить в корзину",
            "en": "Add to cart"
        }
    
    class Cart(Translatable):
        place = {
            "ru": "Оформить за {price}",
            "en": "Place for {price}"
        }
        
        send = {
            "ru": "Отправить",
            "en": "Send"
        }
        
        send_to_check = {
            "ru": "Отправить на проверку",
            "en": "Send to check"
        }
        
        edit = {
            "ru": "Редактировать",
            "en": "Edit"
        }
        
        class OrderConfiguration(Translatable):
            proceed_to_payment = {
                "ru": "Перейти к оплате",
                "en": "Proceed to payment"
            }
        
            use_promocode = {
                "ru": "Использовать промокод",
                "en": "Use a promo code"
            }
            
            use_bonus_money = {
                "ru": "Использовать бонусную валюту",
                "en": "Use the bonus currency"
            }
            
            change_payment_method = {
                "ru": "Изменить метод оплаты",
                "en": "Change the payment method"
            }
            
            choose_payment_method = {
                "ru": "Выбрать метод оплаты ❗️",
                "en": "Choose a payment method ❗️"
            }
            
            i_paid = {
                "ru": "Я оплатил",
                "en": "I paid"
            }
    
    class Orders(Translatable):
        class Infos(Translatable):
            any_question = {
                "ru": "Есть какой-то вопрос?",
                "en": "Any question?"
            }
            
    
    class Profile(Translatable):
        settings = {
            "ru": "Настройки",
            "en": "Settings"
        }
        
        referrals = {
            "ru": "Рефералы",
            "en": "Referrals"
        }
        
        delivery = {
            "ru": "Доставка",
            "en": "Delivery"
        }
        class Settings(Translatable):
            lang = {
                "ru": "Язык",
                "en": "Language"
            }
            
            currency = {
                "ru": "Валюта",
                "en": "Currency"
            }
        
        class Delivery(Translatable):
            menu_change = {
                "ru": "Редактировать",
                "en": "Edit"
            }
            
            menu_not_set = {
                "ru": "Добавить адрес",
                "en": "Add address"
            }
            
            class Edit(Translatable):
                foreign = {
                    "ru": "Зарубеж:",
                    "en": "Foreign:"
                }
                
                change_data = {
                    "ru": "Изменить данные",
                    "en": "Edit data"
                }
                
                delete = {
                    "ru": "Удалить информацию о доставке",
                    "en": "Delete delivery information"
                }
                
class TypedTranslatorHub(TranslatorHub):
    EnumTranslates: EnumTranslates
    UncategorizedTranslates: UncategorizedTranslates
    CommonTranslates: CommonTranslates
    AssortmentTranslates: AssortmentTranslates
    CartTranslates: CartTranslates
    OrdersTranslates: OrdersTranslates
    ProfileTranslates: ProfileTranslates
    ReplyButtonsTranslates: ReplyButtonsTranslates