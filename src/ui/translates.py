import logging
from types import SimpleNamespace
from typing import ClassVar, Optional, Type

from configs.supported import SUPPORTED_LANGUAGES_TEXT
from core.services.placeholders import PlaceholderManager

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
        pm: PlaceholderManager = instance._pm
        
        value = (
            self.translations.get(lang)
            or self.translations.get('en')
            or next(iter(self.translations.values()))
        )

        if isinstance(value, dict):
            def pluralizer(count: int):
                return owner.translate(self._attribute_name, lang, count=count, pm=pm)
            return pluralizer
        else:
            return owner.translate(self._attribute_name, lang, pm=pm)
    
    def translate(self, lang: str, pm: PlaceholderManager = None, count: int = None) -> str:
        if self._owner_class is None:
            raise RuntimeError("TranslationField has no owner_class yet")

        return self._owner_class.translate(self._attribute_name, lang, count=count, pm=pm)
    
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
    
    def __init__(self, lang: str, pm: PlaceholderManager):
        self._lang = lang
        self._pm = pm

    @staticmethod
    def _get_plural_form(lang: str, count: int) -> str:
        if lang == "ru":
            if count % 10 == 1 and count % 100 != 11: return "one"
            elif 2 <= count % 10 <= 4 and (count % 100 < 10 or count % 100 >= 20): return "few"
            else: return "many"
        else: return "one" if count == 1 else "other"

    @classmethod
    def translate(
        cls, 
        attribute: str, 
        lang: str, 
        default_lang: str = 'en', 
        count: int = None, 
        pm: Optional[PlaceholderManager] = None
    ) -> str:
        logger = logging.getLogger(__name__)
        translations = cls._translations.get(attribute, {})

        raw_value = translations.get(lang) or translations.get(default_lang)
        if raw_value is None:
            if translations:
                fallback_lang, raw_value = next(iter(translations.items()))
                logger.warning(f"No '{lang}' or '{default_lang}' translation for '{attribute}', falling back to '{fallback_lang}'.")
            else:
                logger.warning(f"No translations found for '{attribute}'.")
                return "((untranslated))"

        final_string = ""
        if isinstance(raw_value, str) or count is None:
            final_string = raw_value
        else:
            form = cls._get_plural_form(lang, count)
            if form not in raw_value:
                available_forms = ", ".join(raw_value.keys())
                logger.warning(
                    f"Plural form '{form}' not found for '{attribute}' in '{lang}'. "
                    f"Available forms: {available_forms}. "
                    f"Please update translations to include this plural form."
                )
                final_string = f"((missing plural '{form}' for '{attribute}' in '{lang}'))"
            else:
                final_string = raw_value[form]
        
        if pm:
            return pm.process_text(final_string, lang)
        
        return final_string

    
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

    def __init__(self, lang: str, pm: PlaceholderManager):
        self._lang = lang
        self._pm = pm

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
            instance = cls(lang=lang, pm=pm)
            setattr(parent, final_name, instance)

    @classmethod
    def register(cls, translatable_class: Type[Translatable]):
        if translatable_class not in cls._registered_classes:
            cls._registered_classes.append(translatable_class)

    @classmethod
    def get_for_lang(cls, lang: str, pm: PlaceholderManager) -> "TranslatorHub":
        if lang not in cls._cache:
            if lang not in SUPPORTED_LANGUAGES_TEXT.values():
                if lang != "?": logging.getLogger(__name__).warning(f"Can't get TranslatorHub for {lang} language.")
                return cls.get_for_lang('en', pm)
            cls._cache[lang] = TranslatorHub(lang=lang, pm=pm)
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
        
        waiting_for_price_confirmation = {
            "ru": "Ожидает подтверждения цены",
            "en": "Waiting for price confirmation"
        }
        
        waiting_for_forming = {
            "ru": "Ожидает формирования",
            "en": "Waiting for forming"
        }

        waiting_for_payment = {
            "ru": "Ожидает оплаты",
            "en": "Waiting for payment"
        }

        waiting_for_manual_payment_confirm = {
            "ru": "Ожидает подтверждения оплаты",
            "en": "Waiting for payment confirmation"
        }
        
        accepted = {
            "ru": "Принят в работу",
            "en": "Accepted"
        }
        
        waiting_for_photo = {
            "ru": "Ожидает фотографии",
            "en": "Waiting for photo"
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


class DBEntryTranslates(Translatable):
    class ProductConfigurationTranslates(Translatable):
        class Options(Translatable):
            class Poster(Translatable):
                name = {
                    "ru": "Постер",
                    "en": "Poster"
                }
                
                text = {
                    "ru": "Выберите версию постера:",
                    "en": "Select the poster version:"
                }
                
                class Choices(Translatable):
                    class SFW(Translatable):
                        name = {
                            "ru": "SFW",
                            "en": "SFW"
                        }
                        description = {
                            "ru": "Выбрана <b>SFW</b> версия.\n\nУвидеть постер можете на прикрепленном фото.",
                            "en": "The <b>SFW</b> version is selected.\n\nYou can see the poster on the attached photo."
                        }
                    
                    class Medium(Translatable):
                        name = {
                            "ru": "NSFW",
                            "en": "NSFW"
                        }
                        description = {
                            "ru": "Выбрана <b>NSFW</b> версия.\n\nУвидеть постер можете на прикрепленном фото.",
                            "en": "The <b>NSFW</b> version is selected.\n\nYou can see the poster on the attached photo."
                        }
            
            class Size(Translatable):
                name = {
                    "ru": "Размер",
                    "en": "Size"
                }
                
                text = {
                    "ru": "Выберите размер изделия:",
                    "en": "Choose the size of the product:"
                }
                
                class Choices(Translatable):
                    class Small(Translatable):
                        name = {
                            "ru": "Маленький",
                            "en": "Small"
                        }
                        description = {
                            "ru": "Выбран <b>Маленький</b> размер.\n\nУвидеть значения выбранного размера изделия можно на прикрепленном фото.",
                            "en": "Selected <b>Small</b> size.\n\nYou can see all the size values in the attached picture."
                        }
                    
                    class Medium(Translatable):
                        name = {
                            "ru": "Средний",
                            "en": "Medium"
                        }
                        description = {
                            "ru": "Выбран <b>Средний</b> размер.\n\nУвидеть значения выбранного размера изделия можно на прикрепленном фото.",
                            "en": "Selected <b>Medium</b> size.\n\nYou can see all the size values in the attached picture."
                        }
                        
                    class Standart(Translatable):
                        name = {
                            "ru": "Стандартный",
                            "en": "Standart"
                        }
                        description = {
                            "ru": "Выбран <b>Стандартный</b> размер.\n\nУвидеть значения выбранного размера изделия можно на прикрепленном фото.",
                            "en": "Selected <b>Standart</b> size.\n\nYou can see all the size values in the attached picture."
                        }
                    
                    class Large(Translatable):
                        name = {
                            "ru": "Большой",
                            "en": "Large"
                        }
                        description = {
                            "ru": "Выбран <b>Большой</b> размер.\n\nУвидеть значения выбранного размера изделия можно на прикрепленном фото.",
                            "en": "Selected <b>Large</b> size.\n\nYou can see all the size values in the attached picture."
                        }

            class Firmness(Translatable):
                name = {
                    "ru": "Мягкость",
                    "en": "Firmness"
                }
                
                text = {
                    "ru": "Выберите мягкость изделия:",
                    "en": "Choose the firmness of the product:"
                }
                
                class Choices(Translatable):
                    class Soft(Translatable):
                        name = {
                            "ru": "Мягкий",
                            "en": "Soft"
                        }
                        
                        description = {
                            "ru": "Выбран <b>Мягкий</b> силикон.\n\nПример можно увидеть в прикрепленном к сообщению видео.",
                            "en": "<b>Soft</b> silicone is selected.\n\nYou can see an example in the attached video."
                        }
                    
                    class Medium(Translatable):
                        name = {
                            "ru": "Средняя",
                            "en": "Medium"
                        }

                        description = {
                            "ru": "Выбран силикон <b>Средней</b> мягкости.\n\nПример можно увидеть в прикрепленном к сообщению видео.",
                            "en": "<b>Medium-soft</b> silicone is selected.\n\nYou can see an example in the attached video."
                        }
                    
                    class Firm(Translatable):
                        name = {
                            "ru": "Твёрдый",
                            "en": "Firm"
                        }

                        description = {
                            "ru": "Выбран <b>Твёрдый</b> силикон.\n\nПример можно увидеть в прикрепленном к сообщению видео.",
                            "en": "<b>Firm</b> silicone is selected.\n\nYou can see an example in the attached video."
                        }
                    
                    class FirmnessGradation(Translatable):
                        name = {
                            "ru": "Градация жёсткости",
                            "en": "Firmness gradation"
                        }

                        description = {
                            "ru": """Представьте, что изделие не однородное, а состоит из нескольких областей с разной мягкостью, которые <i>плавно</i> перетекают друг в друга.
При выборе двухзонного окраса вы сможете задать только двухзонную градацию жёсткости;
аналогично для трёхзонного окраса — градация жёсткости должна соответствовать числу зон.
После выбора, вам необходимо указать какую жёсткость Вы выбираете для каждой из зон.""",
                            "en": """Imagine that the product is not homogeneous, but consists of several areas with different softness, which <i> smoothly </i> flow into each other.
When choosing a two-zone color, you can only set a two-zone hardness gradation.;
similarly, for a three—zone color, the hardness gradation should correspond to the number of zones.
After selecting, you need to specify which stiffness you choose for each of the zones."""
                        }

            class Color(Translatable):
                name = {
                    "ru": "Окрас",
                    "en": "Color"
                }

                text = {
                    "ru": "Выберите окрас изделия:",
                    "en": "Choose the color of the product:"
                }
                
                class Choices(Translatable):
                    
                    class Canonical(Translatable):
                        name = {
                            "ru": "Каноничный",
                            "en": "Canonical"
                        }

                        description = {
                            "ru": "Выбран <b>каноничный</b> окрас.\n\nПример можете увидеть в прикрепленном к сообщению медиа.",
                            "en": "Selected <b>canonical</b> color.\n\nYou can see an example in the attached media."
                        }
                            
                    class ExistingSet(Translatable):
                        name = {
                            "ru": "Существующий набор",
                            "en": "Existing set"
                        }

                        description = {
                            "ru": "Вы выбрали раскраску {chosen}.",
                            "en": "You have chosen the color {chosen}."
                        }
                    
                    class TwoZone(Translatable):
                        name = {
                            "ru": "Двухзонный",
                            "en": "Two-zone"
                        }

                        description = {
                        "ru": """Опция позволяет окрасить изделие в два разных цвета — каждая зона окрашивается отдельно, с чёткой границей перехода (граница указана на изображении).

В текстовом описании раскраски <b>укажите цвет для каждой зоны</b> (например: <i>верх - синий</i>, <i>низ - прозрачный</i>) и при желании добавьте комментарии по нюансам перехода или эффектам.

Если Вы хотите использовать <b>люминофор, перламутр, блёстки, использовать градиент или неоновые цвета</b>, обязательно:

    <b>1.</b> <b>Упомяните их в описании раскраски</b> (например: <i>верх - фиолетовый с перламутром</i>, <i>низ - зелёный с люминофором</i>).
    <b>2.</b> <b>Включите соответствующие переключатели</b> в меню “Дополнения”.

Базовая двухзонная окраска — бесплатная. Дополнения оплачиваются отдельно.""",

                            "en": """The option allows you to color the product in two different shades — each zone is painted separately, with a clear dividing line (the boundary is shown in the image).

In the coloring description, <b>specify the color for each zone</b> (for example: <i>top – blue</i>, <i>bottom – transparent</i>), and optionally add comments about transition details or special effects.

If you want to use <b>phosphor, pearlescent pigment, glitter, use a gradient or neon colors</b>, make sure to:

    <b>1.</b> <b>Mention them in the coloring description</b> (for example: <i>top – purple with pearlescent effect</i>, <i>bottom – green with phosphor</i>).
    <b>2.</b> <b>Enable the corresponding switches</b> in the “Additionals” menu.

The basic two-zone coloring is free of charge. Add-ons are charged separately."""
                        }
                    
                    class ThreeZone(Translatable):
                        name = {
                            "ru": "Трёхзонный",
                            "en": "Three-zone"
                        }

                        description = {
                        "ru": """Опция позволяет окрасить изделие в три разные зоны, каждая из которых окрашивается отдельно. Границы между зонами указаны на изображении и определяют места перехода цветов.

В текстовом описании раскраски <b>укажите цвет для каждой зоны</b> (например: <i>верх — синий</i>, <i>середина — розовая</i>, <i>низ — прозрачный</i>) и при желании добавьте комментарии по нюансам перехода или эффектам.

Если Вы хотите использовать <b>люминофор, перламутр, блёстки, использовать градиент или неоновые цвета</b>, обязательно:

    <b>1.</b> <b>Упомяните их в описании раскраски</b> (например: <i>верх — фиолетовый с перламутром</i>, <i>середина — розовая с блёстками</i>, <i>низ — зелёный с люминофором</i>).
    <b>2.</b> <b>Включите соответствующие переключатели</b> в меню “Дополнения”.

Дополнения оплачиваются отдельно.""",

                            "en": """The option allows the product to be painted in three different zones, each painted separately. The boundaries between the zones are shown in the image and define where the color transitions occur.

In the coloring description, <b>specify the color for each zone</b> (for example: <i>top — blue</i>, <i>middle — pink</i>, <i>bottom — transparent</i>), and optionally add comments about transition details or special effects.

If you want to use <b>phosphor, pearlescent pigment, glitter, use a gradient or neon colors</b>, make sure to:

    <b>1.</b> <b>Mention them in the coloring description</b> (for example: <i>top — violet with pearlescent effect</i>, <i>middle — pink with glitter</i>, <i>bottom — green with phosphor</i>).
    <b>2.</b> <b>Enable the corresponding switches</b> in the “Additionals” menu.

Add-ons are charged separately."""
                        }
                    
                    class Swirl(Translatable):
                        name = {
                            "ru": "Вихрь",
                            "en": "Swirl"
                        }

                        description = {
                            "ru": """Опция создаёт <b>уникальный вихревой рисунок</b> — хаотичное смешение выбранных Вами цветов, в результате чего получается плавный и равномерный перелив оттенков по всему изделию.
                            
В текстовом описании раскраски <b>укажите от двух до четырёх цветов</b>, которые будут использованы для создания вихря.

Если Вы хотите использовать <b>люминофор, перламутр, блёстки, использовать градиент или неоновые цвета</b>, обязательно:
    <b>1.</b> <b>Упомяните их в описании раскраски</b> (например: <i>вихрь из фиолетового и синего с перламутром</i>).
    <b>2.</b> <b>Включите соответствующие переключатели</b> в меню “Дополнения”.

Дополнения оплачиваются отдельно.""",

                            "en": """The option creates a <b>unique swirl pattern</b> — a chaotic blend of the colors you choose, resulting in a smooth and even transition of shades across the entire product.

In the color description field, <b>specify two to four colors</b> that will be used to create the swirl.

If you want to use <b>phosphor, pearlescent pigment, glitter, use a gradient or neon colors</b>, make sure to:
    <b>1.</b> <b>Mention them in the color description</b> (for example: <i>a swirl of purple and blue with pearlescent effect</i>).
    <b>2.</b> <b>Enable the corresponding switches</b> in the “Additionals” menu.     
    
Add-ons are charged separately."""
                        }
                    
                    class Custom(Translatable):
                        name = {
                            "ru": "Свой",
                            "en": "Custom"
                        }

                        description = {
                            "ru": """Опция позволяет создать <b>уникальный индивидуальный окрас</b> изделия по Вашему описанию. Итоговая стоимость рассчитывается <b>в зависимости от сложности работы</b>.

В текстовом описании раскраски <b>укажите, какие цвета (из меню) и эффекты</b> Вы хотите видеть, а также любые другие пожелания.

Если Вы хотите добавить <b>люминофор, перламутровый пигмент, блёстки, использовать градиент или неоновые цвета</b>, обязательно:
<b>1.</b> <b>Упомяните их</b> в своём описании окраса.
<b>2.</b> <b>Включите соответствующие переключатели</b> в меню “Дополнения”.

Итоговая стоимость кастомного окраса рассчитывается индивидуально и зависит от сложности исполнения. Дополнения оплачиваются отдельно.""",
                            "en": """This option allows you to create a <b>unique, individual paint job</b> based on your description. The final cost is calculated <b>based on the complexity of the work</b>.

In your text description of the paint job, <b>specify which colors and effects</b> you would like to see, as well as any other wishes.

If you want to add <b>luminescent or pearlescent pigment, glitter, use a gradient or neon colors</b>, please ensure you:
    <b>1.</b> <b>Mention them</b> in your paint job description.
    <b>2.</b> <b>Enable the corresponding toggles</b> in the “Additionals” menu.

The final cost for a custom paint job is calculated individually and depends on the complexity of the design. Add-ons are charged separately."""
                    
                        }
                    
                    class Additionals(Translatable):
                        name = {
                            "ru": "Дополнения",
                            "en": "Additionals"
                        }
                        description = {
                            "ru": "Используйте меню ниже, чтобы добавить к окраске дополнительные элементы.",
                            "en": "Use the menu below to add additional elements to the coloring."
                        }
                        
                        class Switches(Translatable):
                            class Gradient(Translatable):
                                name = {
                                    "ru": "Градиент",
                                    "en": "Gradient"
                                }
                                description = {
                                    "ru": "Создаёт плавный и естественный переход от одного цвета к другому. Если использован набор цветов, то градиент будет от верхнего ко второму цвету",
                                    "en": "Creates a smooth and natural transition from one color to another. If a set of colors is used, the gradient will be from the top to the second color."
                                }
                            
                            class Glitter(Translatable):
                                name = {
                                    "ru": "Блёстки",
                                    "en": "Glitter"
                                }
                                description = {
                                    "ru": "Декоративная добавка, размер около 0.2мм, играет на свету. По умолчанию используются серебряные.",
                                    "en": "Decorative additive, about 0.2mm in size, plays in the light. Silver is used by default."
                                }
                        
                            class Shimmer(Translatable):
                                name = {
                                    "ru": "Перламутровый пигмент",
                                    "en": "Shimmer"
                                }
                                description = {
                                    "ru": "Представляет собой порошковый краситель с металлическим сиянием, придающий поверхности интересный перелив и игру света. Является самостоятельным цветом для покраски. (см. Доступные цвета)",
                                    "en": "It is a fine powder with a metallic sheen, giving the surface an interesting iridescence and a play of light. It is an independent color for painting. (see Available colors)"
                                }

                            class NeonColors(Translatable):
                                name = {
                                    "ru": "Неоновые цвета",
                                    "en": "Neon colors"
                                }
                                description = {
                                    "ru": "Отдельные пигменты, способные отражать ультрафиолетовый свет. (см. Доступные цвета)",
                                    "en": "Individual pigments capable of reflecting ultraviolet light. (see Available colors)"
                                }

                            class PhosphorsGroup(Translatable):
                                name = {
                                    "ru": "Люминофоры",
                                    "en": "Phosphors"
                                }
                                description = {
                                    "ru": "Светящиеся пигменты, способные накапливать энергию от ультрафиолетового света и постепенно отдавать её в виде яркого послесвечения. Зеленые и голубые оттенки имеют самое сильное и долгое свечение. Используется как добавка для смешения с цветами.",
                                    "en": "Luminous pigments that can accumulate energy from ultraviolet light and gradually release it in the form of a bright afterglow. Green and blue shades have the strongest and longest glow. It is used as an additive for mixing with colors."
                                }
                                
                                class Switches(Translatable):
                                    class Blue(Translatable):
                                        name = {
                                            "ru": "Синий",
                                            "en": "Blue"
                                        }
                                        
                                    class Cyan(Translatable):
                                        name = {
                                            "ru": "Голубой",
                                            "en": "Cyan"
                                        }

                                    class Green(Translatable):
                                        name = {
                                            "ru": "Зелёный",
                                            "en": "Green"
                                        }
                                    
                                    class Red(Translatable):
                                        name = {
                                            "ru": "Красный",
                                            "en": "Red"
                                        }
                                        
                                    class Purple(Translatable):
                                        name = {
                                            "ru": "Фиолетовый",
                                            "en": "Purple"
                                        }
                                    
                                    class White(Translatable):
                                        name = {
                                            "ru": "Белый",
                                            "en": "White"
                                        }
                                    
                        
                    class AvailableColors(Translatable):
                        name = {
                            "ru": "Доступные цвета",
                            "en": "Available colors"
                        }

                        text = {
                            "ru": "На прикрепленном медиафайле отображены стандартные цвета для ознакомления.",
                            "en": "The attached media file displays standard colors for review."
                        }
            
class UncategorizedTranslates(Translatable):
    oopsie = {
        "ru": "Упс! Прости, мне нужно начать заново...",
        "en": "Oops! I'm sorry, I need to start over..."
    }
    
    input_message_too_long = {
        "ru": "Ваше сообщение слишком длинное! Попробуйте сократить его до 1024 символов.",
        "en": "Your message is too long! Try shortening it to 1024 characters."
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
    
    what_is_this = {
        "ru": "Что это?",
        "en": "What is this?"
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
    
    people = {
        "ru": {"one": "человека", "few": "человека", "many": "человек"},
        "en": {"one": "person", "other": "people"}
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
    
    maturity_question = {
        "ru": "Вам есть 18 лет?",
        "en": "Are you at least 18 years old?"
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
        "ru": "Введите номер готового пресета (латиница):",
        "en": "Select the preset number (Latin alphabet):"
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
        "ru": "Эта опция недоступна, пока Вы выбрали {path}.",
        "en": "This option is unavailable while you have selected {path}."
    }

    cannot_price = {
        "ru": "Определить точную цену товара невозможно из-за индивидуальных параметров.",
        "en": "It is impossible to determine the exact price of the product due to individual parameters."
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
        "ru": "В Вашей корзине нет товаров!",
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
    
    # delivery_not_configured = {
    #     "ru": "Перед оформлением заказа необходимо настроить доставку.",
    #     "en": "Before placing an order, you need to set up delivery."
    # }
        
    cart_price_confirmation = {
        "ru": "В Вашей корзине есть товары с индивидуальными параметрами, поэтому мы рассчитаем итоговую цену вручную.\n\nОтправьте заказ на подтверждение, и мы пришлем уведомление, как только все будет готово. После этого можно будет перейти к оплате.\n\nБазовая стоимость: {price}",
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
            "ru": "На данный момент Вас нет бонусных денег.\nУзнать подробнее о них Вы можете в меню Профиль —> Рефералы.",
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

Поскольку это не автоматизируемый метод оплаты, произведенный Вами платеж будет проверен вручную. (Вам будет выслано уведомление)
После оплаты заказа нажмите соответствующую кнопку ниже:""",
        }
        
        manual_payment_confirmation_sended = {
            "ru": "Заказ сформирован и ожидает подтверждения оплаты. ✅\nПосле подтверждения бот вышлет Вам уведомление. Для дополнительной информации о заказе Вы можете перейти в соответствующее меню.",
            "en": "The order has been formed and is awaiting payment confirmation. ✅\nAfter confirmation, the bot will send you a notification. For more information about the order, you can go to the corresponding menu."
        }

class OrdersTranslates(Translatable):
    no_orders = {
        "ru": "У Вас нет заказов.",
        "en": "You have no orders."
    }
    
    menu = {
        "ru": "Связанные с Вами заказы:\n\n{orders_info}\n\nВведите номер заказа с которым Вы хотите взаимодействовать:",
        "en": "Orders related to you:\n\n{orders_info}\n\nEnter the order number you want to interact with:"
    }
    
    order_viewing_menu = {
        "ru": """<b>Заказ #{order_puid}</b> от {order_forming_date}
{order_entries_description}        

Статус заказа: {order_status}{delivery_info}{payment_method}{promocode_info}{bonus_money_info}

Суммарная стоимость товаров: {products_price}
{price_info}
""",
        "en": """<b>Order #{order_puid}</b> from {order_forming_date}
{order_entries_description}

Order status: {order_status}{delivery_info}{payment_method}{promocode_info}{bonus_money_info}

Total cost of goods: {products_price}
{price_info}"""
    }
    
    payment_method = {
        "ru": "\nСпособ оплаты: {info}",
        "en": "\nPayment method: {info}"
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
            "ru": "Если Вы считаете, что что-то идет не так, напишите @TechnoZmeyka.",
            "en": "If you think something is going wrong, write to @TechnoZmeyka."
        }

class ProfileTranslates(Translatable):
    menu = {
        "ru": "Выберите пункт Вашего профиля:",
        "en": "Select an item in your profile:"
    }

    current_bonus_balance = {
        "ru": "На Вашем бонусном счету — {balance}.",
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
        "ru": "Внимание! Конвертировать валюту в следующий раз Вы сможете только через неделю!",
        "en": "Conversion will be made at the rate from {fromVal} to {toVal}."
    }
    
    delivery_info_price_sent_to_confirmation = {
        "ru": "Ваша доставка ожидает подтверждения цены.",
        "en": "Your delivery is waiting for price confirmation."
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
        
    class Referrals(Translatable):
        ask_for_join = {
            "ru": "Вы хотите вступить в нашу реферальную программу?",
            "en": "Do you want to join our referral program?"
        }
        
        what_is_this = {
            "ru": """🎁 Реферальная система

Зарабатывай бонусы или реальные выплаты, приглашая друзей или подписчиков!

👤 Для пользователей:
Просто вступи в программу и получи свою персональную ссылку.
  — Пригласи друга
  — С его первого заказа ты получишь 5% на бонусный счёт
  — Бонусами можно оплатить часть следующего заказа

📢 Для владельцев каналов:
После вступления напиши @TechnoZmeyka — он активирует партнёрский статус.
Ты будешь получать выплаты за заказы по договорённости.""",
            "en": """🎁 Referral system

Earn bonuses or real payouts by inviting friends or subscribers!

👤 For users:
Just join the program and get your personal link.
  — Invite a friend
  — From his first order, you will receive 5% to the bonus account
  — You can use bonuses to pay for part of the next order.

📢 For channel owners:
After joining, write to @TechnoZmeyka — he will activate the partner status.
You will receive payments for orders by agreement."""
        }
        
        menu_customer = {
            "ru": """👥 Реферальная система

Вы пригласили: {invited_customers} {people}
Из них сделали хотя бы один заказ: {ordered_once}

Приглашайте друзей и получайте бонус за их первый заказ! 🎁
Сейчас у Вас {bonus_balance} на бонусном счету.""",
            "en": """👥 Referral program

You invited: {invited_customers} {people}
Of them made at least one order: {ordered_once}

Invite your friends and get a bonus for their first order! 🎁
Now you have {bonus_balance} on your bonus account."""
        }
        
        menu_channel = {
            "ru": """👥 Реферальная система

Вы пригласили: {invited_customers} {people}
Из них сделали хотя бы один заказ: {ordered_once}""",
            "en": """👥 Referral program

You invited: {invited_customers} {people}
Of them made at least one order: {ordered_once}"""
        }
        
        invitation_link_view = {
            "ru": """Ваша ссылка для приглашения: {link}
Однако Вы можете использовать и вариант ниже, со скрытой ссылкой:""",
            "en": """Your invitation link: {link}
However, you can also use the option below, with a hidden link:"""
        }
        
        
    class Delivery(Translatable):
    
        menu = {
            "ru": """Ранее заполненная Вами информация о доставке:
  Способ доставки: {delivery_service} ({service_price}), {delivery_req_lists_name}
{requirements}

Изменить информацию о доставке Вы можете используя кнопки ниже:""",
            "en": """The shipping information you filled in earlier:
  Shipping method: {delivery_service} ({service_price}), {delivery_req_lists_name}
{requirements}

You can change the delivery information using the buttons below:"""
        }
        
        menu_not_configured = {
            "ru": "Перед формированием заказа, Вам необходимо заполнить информацию о доставке.",
            "en": "Before forming an order, you need to fill in the delivery information."
        }
        
        waiting_for_manual_confirmation = {
            "ru": "Ваша доставка ожидает ручного подтверждения.",
            "en": "Your delivery is waiting for manual confirmation."
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
        
        send_to_manual_confirmation_text = {
            "ru": "Вы уверены что хотите отправить доставку на ручное подтверждение стоимости?",
            "en": "Are you sure you want to send the delivery to manual confirmation?"
        }
      
class NotificatorTranslates(Translatable):
    
    class User(Translatable):
        admin_message = {
            "ru": "Сообщение выше было направлено от Администратора. Если хотите на него ответить, напишите @{username}",
            "en": "The message above was sent from the Administrator. If you want to reply to it, write @{username}"
        }
        
        inviter_reward = {
            "ru": "Вам было начислено {reward} за первый заказ приглашённого Вами пользователя.\nТеперь у Вас {balance} на бонусном счету.",
            "en": "You have been awarded {reward} for the first order of the user you invited.\nNow you have {balance} in your bonus account."
        }
    
    class Delivery(Translatable):
        delivery_price_confirmed = {
            "ru": "Стоимость Вашей доставки подтверждена. Теперь Вы можете оформлять заказы.",
            "en": "Your delivery price has been confirmed. You can now place orders."
        }
        
        delivery_price_rejected = {
            "ru": "Вашу доставку отклонили. Вы можете изменить информацию о доставке и попробовать еще раз.",
            "en": "Your delivery was rejected. You can change your delivery information and try again."
        }
        
        delivery_price_rejected_with_reason = {
            "ru": "Вашу доставку отклонили. Вы можете изменить информацию о доставке и попробовать еще раз.\nПричина: {reason}",
            "en": "Your delivery was rejected. You can change your delivery information and try again.\nReason: {reason}"
        }
    
    class Order(Translatable):
        order_price_confirmed = {
            "ru": "Стоимость Вашего заказа была подтверждена. Вы можете продолжить формирование заказа в меню Заказы.",
            "en": "Your order price has been confirmed. You can continue forming your order in the Orders menu."
        }
        
        order_state_changed = {
            "ru": "Статус Вашего заказа {order_puid} изменился на \"{order_state}\".",
            "en": "The status of your order {order_puid} has changed to \"{order_state}\"."
        }
        
        order_payment_accepted = {
            "ru": "Мы получили оплату по заказу {order_puid}. Вы будете получать уведомления о изменении его статуса",
            "en": "We have received payment for your order {order_puid}. You will receive notifications about changes in its status"
        }
        
        order_unformed = {
            "ru": "Ваш заказ {order_puid} был расфомирован.",
            "en": "Your order {order_puid} was unformed."
        }

        order_unformed_with_reason = {
            "ru": "Ваш заказ {order_puid} был расфомирован.\nПричина: {reason}",
            "en": "Your order {order_puid} was unformed.\nReason: {reason}"
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
        
        extra_options = {
            "ru": "Доп. опции",
            "en": "Ext. Options"
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
        
        continue_forming = {
            "ru": "Продолжить формирование",
            "en": "Continue forming"
        }
        
        view_comment = {
            "ru": "Посмотреть комментарий",
            "en": "View comment"
        }
        
        view_comments = {
            "ru": "Посмотреть комментарии",
            "en": "View comments"
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
            
        class Referrals(Translatable):
            invitation_link = {
                "ru": "Пригласительная ссылка",
                "en": "Invitation link"
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
    DBEntryTranslates: DBEntryTranslates
    EnumTranslates: EnumTranslates
    UncategorizedTranslates: UncategorizedTranslates
    CommonTranslates: CommonTranslates
    AssortmentTranslates: AssortmentTranslates
    CartTranslates: CartTranslates
    OrdersTranslates: OrdersTranslates
    ProfileTranslates: ProfileTranslates
    ReplyButtonsTranslates: ReplyButtonsTranslates