class TranslationMeta(type):
    """Метакласс для автоматической организации переводов"""

    def __new__(cls, name, bases, attrs):
        # Собираем атрибуты-переводы со всех родительских классов
        translations = {}
        reverse_translations = {}

        # Обрабатываем родительские классы
        for base in bases:
            if hasattr(base, '_translations'):
                translations.update(base._translations)
            if hasattr(base, '_reverse_translations'):
                for lang, texts in base._reverse_translations.items():
                    reverse_translations.setdefault(lang, {}).update(texts)

        # Обрабатываем текущий класс
        for attr_name, value in attrs.items():
            if isinstance(value, dict) and all(isinstance(k, str) for k in value.keys()):
                translations[attr_name] = value
                # Строим обратный словарь
                for lang, text in value.items():
                    reverse_translations.setdefault(lang, {})[text] = attr_name

        # Сохраняем в классе
        attrs['_translations'] = translations
        attrs['_reverse_translations'] = reverse_translations

        return super().__new__(cls, name, bases, attrs)


class Translatable(metaclass=TranslationMeta):
    """Базовый класс для переводимых объектов"""


    @classmethod
    def translate(cls, attribute: str, lang: str, default_lang: str = 'en') -> str:
        """Получить перевод для указанного атрибута"""
        translations = cls._translations.get(attribute, {})
        return translations.get(lang, translations.get(default_lang, attribute))

    @classmethod
    def get_attribute(cls, text: str, lang: str) -> str:
        """Получить имя атрибута по переводу"""
        return cls._reverse_translations.get(lang, {}).get(text)
    
    @classmethod
    def get_all_attributes(cls, lang: str) -> list:
        """Получить имена всех атрибутов класса по переводу"""
        return cls._reverse_translations.get(lang, {}).keys()

    @classmethod
    def supported_languages(cls) -> set:
        """Получить все поддерживаемые языки"""
        return {
            lang
            for trans in cls._translations.values()
            for lang in trans.keys()
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
    # name = {
    #     "ru": "",
    #     "en": ""
    # }

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
        "ru": "Введите текст-описание кастомного окраса:",
        "en": "Enter a text description of your custom coloring:"
    }

    switches_enter = {
        "ru": "Переключайте опции кнопками ниже:",
        "en": "Switch the options using the buttons below:"
    }

    no_products_in_category = {
        "ru": "Простите! Судя по всему, товаров данной категории не существует.",
        "en": "Sorry! Apparently, there are no products in this category."
    }

    cant_find_that_category = {
        "ru": "Такой категории нет!",
        "en": "There is no such category!"
    }

    total = {
        "ru": "Итоговая стоимость: ",
        "en": "Total: "
    }

    additionals = {
        "ru": "Другое:",
        "en": "Other:"
    }

    cannot_price = {
        "ru": "Определить точную цену товара невозможно.",
        "en": "It is impossible to determine the exact price of the product."
    }

    approximate_price = {
        "ru": "Приблизительная цена: ",
        "en": "Approximate price: "
    }

    currently_selected = {
        "ru": "На данный момент выбраны такие настройки:",
        "en": "The following settings are currently selected: "
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
            "ru": "Ваша текущая валюта — {currency}.\nВыберите ввлюту:",
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
        
    class Delivery(Translatable):
    
        menu = {
            "ru": """Честно, не ебу какой сюда текст вставить, на тут вот инфа о уже настроенной доставке:
    Способ доставки: {delivery_service}
{requirements}
Изменить информацию о доставке вы можете используя кнопку ниже:""",
            "en": """Честно, не ебу какой сюда текст вставить, на тут вот инфа о уже настроенной доставке:
    Способ доставки: {delivery_service}
{requirements}
Изменить информацию о доставке вы можете используя кнопку ниже:"""
        }
        
        menu_not_configured = {
            "ru": "Лееее ишак чо не сконфигурировал свою доставку чорт баля, кнопки ниже решат алёу",
            "en": "Лееее ишак чо не сконфигурировал свою доставку чорт баля, кнопки ниже решат алёу"
        }
        
        is_foreign_text = { # Россия / За рубеж
            "ru": "Куда будет осуществляться доставка?",
            "en": ""
        }
        
        foreign_choice_rus = {
            "ru": "🇷🇺 Россия",
            "en": "🇷🇺 Russia"
        }
        
        foreign_choice_foreign = {
            "ru": "🌍 За рубеж",
            "en": "🌍 Foreign"
        }
        
        service_text = { # Почта России / Боксберри
            "ru": "Выберите сервис доставки:",
            "en": ""
        }
        
        requirements_list_text = { # По телефону / По ФИО и адресу
            "ru": "Выберите способ оформления доставки:",
            "en": ""
        }
        
        requirement_value_text = { # Телефон / Адрес; пишите номер в формате +7xxxxxxxxxx
            "ru": "Примечание:\n{description}\n\nВведите <b>{name}</b>:",
            "en": ""
        }

class InlineButtonsTranslates(Translatable):
    details = {
        "ru": "Подробнее",
        "en": "Details"
    }

    add_to_cart = {
        "ru": "Добавить в корзину",
        "en": "Add to cart"
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
                    "ru": "Зарубеж: ",
                    "en": "Foreign: "
                }
                
                change_data = {
                    "ru": "Изменить данные",
                    "en": "Edit data"
                }