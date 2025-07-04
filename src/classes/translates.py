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

    back = {
        "ru": "Назад",
        "en": "Back"
    }

    finish = {
        "ru": "Закончить",
        "en": "Finish"
    }

    # currency_sign = {
    #     "ru": "₽",
    #     "en": "$"
    # }

    cancel = {
        "ru": "Отмена",
        "en": "Cancel"
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

    about_menu = {
        "ru": "о нас",
        "en": "about us"
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