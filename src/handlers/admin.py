from io import BytesIO

from aiogram.fsm.context import FSMContext

from aiogram import Bot, Router, html, F
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.types import Message, BufferedInputFile

from src.classes import keyboards
from src.classes.db import *
from src.classes.middlewares import RoleCheckMiddleware

router = Router(name="admin")
middleware = RoleCheckMiddleware("admin")

router.message.middleware.register(middleware)
router.callback_query.middleware.register(middleware)




@router.message(Command("save_image"))
async def image_saving_handler(message: Message, command: CommandObject, state: FSMContext, db: DB, lang: str) -> None:
    raw = await message.bot.download(message.document)

    msg_id = await message.answer_photo(photo=BufferedInputFile(
        raw.read(),
        filename="image.jpg"
    )
    )
    await message.answer(msg_id.photo[-1].file_id)

@router.message(Command("save_video"))
async def image_saving_handler(message: Message, command: CommandObject, state: FSMContext, db: DB, lang: str) -> None:
    raw = await message.bot.download(message.document)

    msg_id = await message.answer_video(video=BufferedInputFile(
        raw.read(),
        filename="image.mp4"
    )
    )
    await message.answer(msg_id.video.file_id)

@router.message(Command("add_cats"))
async def cats_handler(message: Message, command: CommandObject, state: FSMContext, db: DB, lang: str) -> None:
    cat = Category(
        name="dildos",
        localized_name=LocalizedString(data={
                "ru": "Дилдо",
                "en": "Dildos"
            }))
    await db.categories.save(cat)
    cat = Category(
        name="masturbators",
        localized_name=LocalizedString(data={
                "ru": "Мастурбаторы",
                "en": "Masturbators"
            }))
    await db.categories.save(cat)
    cat = Category(
        name="anal_plugs",
        localized_name=LocalizedString(data={
                "ru": "Анальные пробки",
                "en": "Anal plugs"
            }))
    await db.categories.save(cat)

    cat = Category(
        name="other",
        localized_name=LocalizedString(data={
                "ru": "Другое",
                "en": "Other"
            }))
    await db.categories.save(cat)


@router.message(Command("add_product"))
async def image_saving_handler(message: Message, command: CommandObject, state: FSMContext, db: DB, lang: str) -> None:
    configuration = ProductConfiguration(options={
        "Размер": ConfigurationOption(
            name=LocalizedString(data={
                "ru": "Размер",
                "en": "Size"
            }),
            text=LocalizedString(data={
                "ru": "Выберите размер изделия:",
                "en": "Choose the size of the product:"
            }),
            chosen=2,
            choices=[
                ConfigurationChoice(
                    label=LocalizedString(data={"ru":"Маленький", "en":"Small"}),
                    photo_id="AgACAgIAAxkDAAIEvmgdCZ7FHIjc4ZWxlEr1-RKo4mamAALx8zEb4TjpSMnWZTFndXzfAQADAgADeQADNgQ",
                    description=LocalizedString(data={
                        "ru": "Выбран <b>Маленький</b> размер.\n\nУвидеть значения выбранного размера изделия можно на прикрепленном фото.",
                        "en": "Selected <b>Small</b> size.\n\nYou can see all the size values in the attached picture."}),

                    price=LocalizedPrice(data={"ru":-1000.00, "en":-30.00})
                ),
                ConfigurationChoice(
                    label=LocalizedString(data={"ru":"Средний", "en":"Medium"}),
                    photo_id="AgACAgIAAxkDAAIEuWgdAVwm5m-WAtrHRu_LZrlvUa-MAAKS8zEb4TjpSHff2pId4ujoAQADAgADeQADNgQ",
                    description=LocalizedString(data={
                        "ru": "Выбран <b>Средний</b> размер.\n\nУвидеть значения выбранного размера изделия можно на прикрепленном фото.",
                        "en": "Selected <b>Medium</b> size.\n\nYou can see all the size values in the attached picture."})
                ),
                ConfigurationChoice(
                    label=LocalizedString(data={"ru":"Большой", "en":"Big"}),
                    photo_id="AgACAgIAAxkDAAIEwmgdCcaeJbdRNP39SPUifkgCY0T1AAL28zEb4TjpSODUEAABvCEBnAEAAwIAA3kAAzYE",
                    description=LocalizedString(data={
                        "ru": "Выбран <b>Большой</b> размер.\n\nУвидеть значения выбранного размера изделия можно на прикрепленном фото.",
                        "en": "Selected <b>Big</b> size.\n\nYou can see all the size values in the attached picture."}),

                    price=LocalizedPrice(data={"ru":1000.00, "en":30.00})
                )
            ]
        ),
        "Мягкость": ConfigurationOption(
            name=LocalizedString(data={
                "ru": "Мягкость",
                "en": "Firmness"
            }),
            text=LocalizedString(data={
                "ru": "Выберите мягкость изделия:",
                "en": "Choose the firmness of the product:"
            }),
            chosen=2,
            choices=[
                ConfigurationChoice(
                    label=LocalizedString(data={"ru": "Мягкий", "en": "Soft"}),
                    video_id="BAACAgIAAxkDAAIEtGgc93O_W9FxMWJ7D859YU2tP9fxAAJGdwAC4TjpSKfM23poBFmlNgQ",
                    description=LocalizedString(data={
                        "ru": "Выбран <b>Мягкий</b> силикон.\n\nПример можно увидеть в прикрепленном к сообщению видео.",
                        "en": "<b>Soft</b> silicone is selected.\n\nYou can see an example in the attached video."})
                ),
                ConfigurationChoice(
                    label=LocalizedString(data={"ru": "Средний", "en": "Medium"}),
                    video_id="BAACAgIAAxkDAAIEtGgc93O_W9FxMWJ7D859YU2tP9fxAAJGdwAC4TjpSKfM23poBFmlNgQ",
                    description=LocalizedString(data={
                        "ru": "Выбран силикон <b>Средней</b> мягкости.\n\nПример можно увидеть в прикрепленном к сообщению видео.",
                        "en": "<b>Medium-soft</b> silicone is selected.\n\nYou can see an example in the attached video."})
                ),
                ConfigurationChoice(
                    label=LocalizedString(data={"ru": "Твёрдый", "en": "Firm"}),
                    video_id="BAACAgIAAxkDAAIEtGgc93O_W9FxMWJ7D859YU2tP9fxAAJGdwAC4TjpSKfM23poBFmlNgQ",
                    description=LocalizedString(data={
                        "ru": "Выбран <b>Твёрдый</b> силикон.\n\nПример можно увидеть в прикрепленном к сообщению видео.",
                        "en": "<b>Firm</b> silicone is selected.\n\nYou can see an example in the attached video."})
                )
            ]
        ),
        "Окрас": ConfigurationOption(
            name=LocalizedString(data={
                "ru": "Окрас",
                "en": "Color"
            }),
            text=LocalizedString(data={
                "ru": "Что вы хотите сделать?",
                "en": "What do you want to do?"
            }),
            chosen=1,
            choices=[
                ConfigurationChoice(
                    label=LocalizedString(data={"ru": "Выбрать существующий", "en": "Select an existing one"}),
                    video_id="BAACAgIAAxkDAAIEtGgc93O_W9FxMWJ7D859YU2tP9fxAAJGdwAC4TjpSKfM23poBFmlNgQ",
                    existing_presets=True,
                    existing_presets_chosen=1,
                    existing_presets_quantity=3,

                    description=LocalizedString(data={
                        "ru": "Вы выбрали раскраску под номером CHOSEN.",
                        "en": "You have chosen the color number CHOSEN."})
                ),
                ConfigurationChoice(
                    label=LocalizedString(data={"ru": "Своя раскраска", "en": "Custom colors"}),
                    video_id="BAACAgIAAxkDAAIEtGgc93O_W9FxMWJ7D859YU2tP9fxAAJGdwAC4TjpSKfM23poBFmlNgQ",
                    is_custom_input=True,

                    description=LocalizedString(data={
                        "ru": "Здесь типо текст где\nэээээ\nну типо тут то что можно менять/какие цвета, цены на них же ээ да",
                        "en": "Here's like a text where\nuhhhhh\n I'm like here's what you can change/what colors, the prices for them are the same, uh yes"})
                ),
                ConfigurationSwitches(
                    label=LocalizedString(data={"ru": "Дополнительно", "en": "Additional"}),
                    video_id="BAACAgIAAxkDAAIEtGgc93O_W9FxMWJ7D859YU2tP9fxAAJGdwAC4TjpSKfM23poBFmlNgQ",
                    description=LocalizedString(data={
                        "ru": "Тут чисто инфа про сами свитчи и про то что если надо на отдельные части, то указывать в коментах, ну и ляля",
                        "en": "Тут чисто инфа про то что если надо на отдельные части, то указывать в коментах, ну и ляля"}),
                    switches=[
                        ConfigurationSwitch(
                            name=LocalizedString(data={"ru": "Блёстки", "en": "Glitter"}),
                            price=LocalizedPrice(data={"ru":100.00, "en":6.00})

                        ),
                        ConfigurationSwitch(
                            name=LocalizedString(data={"ru": "Шиммер", "en": "Shimmer"}),
                            price=LocalizedPrice(data={"ru": 100.00, "en": 6.00})

                        ),
                        ConfigurationSwitch(
                            name=LocalizedString(data={"ru": "Люминофор", "en": "Phosphor"}),
                            price=LocalizedPrice(data={"ru": 100.00, "en": 6.00})

                        )
                    ]
                )
            ]
        )
    })

    product = Product(
        name=LocalizedString(data={
            "ru":"Дракон Хайден",
            "en":"Hiden Dragon"}
        ),
        category="dildos",
        short_description=LocalizedString(data={
            "ru":"Заглушка хд",
            "en":"Заглушка хд"}
        ),
        short_description_photo_id="AgACAgIAAxkDAAIEqmgc2mt5nYStZBhwifMHuicCdPk5AAJo8TEb4TjpSPRjXA9O3dgSAQADAgADeQADNgQ",
        long_description=LocalizedString(data={
            "ru":"""<blockquote expandable>Нежное сияние пурпурной драконьей чешуи под лучами алого заката. Хайден всегда знает, как позаботиться о своём любимом партнёре. Мягко обхватывая тебя своими опытными лапками, чутко лаская чувствительные зоны, он приближается всё ближе и ближе, заставляя твоё тело легко подрагивать от возбуждения. Он улавливает твоё сбитое дыхание, чуть улыбаясь от удовольствия... 

Его кончик нежно входит в тебя, заставляя постанывать и дрожать еще сильнее. Постепенно расширяясь, мягко входят сплетения, доходя до окончательно добивающего узла... 
Сильный и нежный, дракон Хайден будет идеальным партнёром, дарящим мягкие ласки и доминирущее превосходство, ведь все бурные фантазии, воплощаемые в жизнь, зависят только от твоего желания~</blockquote>

Присоска идет в комплекте!""",
            "en":"Hiden Dragon"}
        ),
        long_description_photo_id="AgACAgIAAxkDAAIEqmgc2mt5nYStZBhwifMHuicCdPk5AAJo8TEb4TjpSPRjXA9O3dgSAQADAgADeQADNgQ",
        base_price=LocalizedPrice(data={
            "ru": 5000.00,
            "en": 100.00
        }),
        configuration_photo_id="AgACAgIAAxkDAAIEqmgc2mt5nYStZBhwifMHuicCdPk5AAJo8TEb4TjpSPRjXA9O3dgSAQADAgADeQADNgQ",
        configuration=configuration
    )

    await db.products.insert(product, "dildos", db)


@router.message(Command("add_addit"))
async def addit(message: Message, command: CommandObject, state: FSMContext, db: DB, lang: str) -> None:
    additional = ProductAdditional(
        name=LocalizedString(data={
            "ru":"Дракон Хайден",
            "en":"Hiden Dragon"}
        ),
        category="dildos",
        short_description=LocalizedString(data={
            "ru":"Заглушка хд",
            "en":"Заглушка хд"}
        ),
        price=LocalizedPrice(data={"ru": 1000, "en": 10})
    )

    await db.additionals.save(additional)

@router.message(Command("get"))
async def getto(message: Message, command: CommandObject, state: FSMContext, db: DB, lang: str) -> None:
    additional = ProductAdditional(
        name=LocalizedString(data={
            "ru":"Страпон",
            "en":"Strap onchik"}
        ),
        category="dildos",
        short_description=LocalizedString(data={
            "ru":"Ну там эта кароче хуйня чтобы надеть на пояс и ебать ок да",
            "en":"Ну там эта кароче хуйня чтобы надеть на пояс и ебать ок да"}
        ),
        price=LocalizedPrice(data={"ru": 400, "en": 10}),
        disallowed_products=[]
    )
    await db.additionals.save(additional)

    print(await db.additionals.get("dildos", PydanticObjectId("681fc67be2f9eecf62c8a750")))