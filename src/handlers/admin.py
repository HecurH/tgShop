from aiogram.fsm.context import FSMContext

from aiogram import Router
from aiogram.filters import CommandObject, Command
from aiogram.types import Message, BufferedInputFile

from src.classes.db import *
from src.classes.helper_classes import Context
from src.classes.middlewares import RoleCheckMiddleware

router = Router(name="admin")
middleware = RoleCheckMiddleware("admin")

router.message.middleware.register(middleware)
router.callback_query.middleware.register(middleware)




@router.message(Command("save_image"))
async def image_saving_handler(_, ctx: Context) -> None:
    raw = await ctx.message.bot.download(ctx.message.document)

    msg_id = await ctx.message.answer_photo(photo=BufferedInputFile(
        raw.read(),
        filename="image.jpg"
    )
    )
    await ctx.message.answer(msg_id.photo[-1].file_id)

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
    configuration = ProductConfiguration(options=[
        ConfigurationOption(
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

                    price=LocalizedPrice(data={"RUB":-1000.00, "USD":-30.00})
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

                    price=LocalizedPrice(data={"RUB":1000.00, "USD":30.00})
                )
            ]
        ),
        ConfigurationOption(
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
        ConfigurationOption(
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
                        "ru": "Вы выбрали раскраску под номером {chosen}.",
                        "en": "You have chosen the color number {chosen}."})
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
                            price=LocalizedPrice(data={"RUB":100.00, "USD":6.00})

                        ),
                        ConfigurationSwitch(
                            name=LocalizedString(data={"ru": "Шиммер", "en": "Shimmer"}),
                            price=LocalizedPrice(data={"RUB": 100.00, "USD": 6.00})

                        ),
                        ConfigurationSwitch(
                            name=LocalizedString(data={"ru": "Люминофор", "en": "Phosphor"}),
                            price=LocalizedPrice(data={"RUB": 100.00, "USD": 6.00})

                        )
                    ]
                )
            ]
        )
    ])

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
            "RUB": 5000.00,
            "USD": 100.00
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
        price=LocalizedPrice(data={"RUB": 1000, "USD": 10})
    )

    await db.additionals.save(additional)
    
@router.message(Command("add_delivery_services"))
async def addit(message: Message, command: CommandObject, ctx: Context) -> None:
    service = DeliveryService(
        name=LocalizedString(data={
            "ru":"Почта России",
            "en":"Russian Post"
            }
        ),
        requirements_options=[
            DeliveryRequirementsList(
                name=LocalizedString(data={
                    "ru":"По номеру телефона",
                    "en":"By phone number"
                    }
                ),
                description=LocalizedString(data={
                    "ru":"описание того что почта россии может принимать отправления и по номеру телефона блахблах\nСервис доступен при условии разрешения получателем принимать посылки по номеру телефона.\nПодключить функцию можно в Личном кабинете или в мобильном приложении Почты России",
                    "en":"сначала на русском текст нормально надо написать про почту, а потом уже на английском емае"
                    }
                ),
                requirements=[
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"Номер телефона",
                            "en":"Phone number"
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"пишите номер в формате +7xxxxxxxxxx",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    )
                ]
            ),
            DeliveryRequirementsList(
                name=LocalizedString(data={
                    "ru":"По ФИО и адресу",
                    "en":"By full name and address"
                    }
                ),
                description=LocalizedString(data={
                    "ru":"описание стандартного метода отправки посылок почтой росиси",
                    "en":"на русском сначала блин давай"
                    }
                ),
                requirements=[
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"ФИО",
                            "en":"Full name"
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"пишите типо сюда свою Фамилию, Имя и Отчество лол",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    ),
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"Полный адрес",
                            "en":"Address"
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"При написании адреса не забудьте указать индекс, область, район, наименование населенного пункта и дальше змейка сам пиши я не ибу",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    )
                ]
            )           
        ]
    )
    
    cdek = DeliveryService(
        name=LocalizedString(data={
            "ru":"CDEK",
            "en":"CDEK"
            }
        ),
        requirements_options=[
            DeliveryRequirementsList(
                name=LocalizedString(data={
                    "ru":"По номеру телефона и адресу ПВЗ",
                    "en":""
                    }
                ),
                description=LocalizedString(data={
                    "ru":"описание чего-то там не знаю чего",
                    "en":"сначала на русском текст нормально надо"
                    }
                ),
                requirements=[
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"Номер телефона",
                            "en":"Phone number"
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"пишите номер в формате +7xxxxxxxxxx",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    ),
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"Полный адрес пункта выдачи",
                            "en":""
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"При написании адреса не забудьте перепроверить все ишак дражайший вы наш",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    )
                ]
            ) 
        ]
    )
    
    boxberry = DeliveryService(
        name=LocalizedString(data={
            "ru":"Boxberry",
            "en":"Boxberry"
            }
        ),
        requirements_options=[
            DeliveryRequirementsList(
                name=LocalizedString(data={
                    "ru":"По номеру телефона и адресу ПВЗ",
                    "en":""
                    }
                ),
                description=LocalizedString(data={
                    "ru":"описание чего-то там не знаю чего",
                    "en":"сначала на русском текст нормально надо"
                    }
                ),
                requirements=[
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"Номер телефона",
                            "en":"Phone number"
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"пишите номер в формате +7xxxxxxxxxx",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    ),
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"Полный адрес пункта выдачи",
                            "en":""
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"При написании адреса не забудьте перепроверить все ишак дражайший вы наш",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    )
                ]
            ) 
        ]
    )
    
    ya_delivery = DeliveryService(
        name=LocalizedString(data={
            "ru":"Яндекс Доставка",
            "en":"Yandex Delivery"
            }
        ),
        requirements_options=[
            DeliveryRequirementsList(
                name=LocalizedString(data={
                    "ru":"По номеру телефона и адресу ПВЗ",
                    "en":""
                    }
                ),
                description=LocalizedString(data={
                    "ru":"описание чего-то там не знаю чего",
                    "en":"сначала на русском текст нормально надо"
                    }
                ),
                requirements=[
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"Номер телефона",
                            "en":"Phone number"
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"пишите номер в формате +7xxxxxxxxxx",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    ),
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"Полный адрес пункта выдачи",
                            "en":""
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"При написании адреса не забудьте перепроверить все ишак дражайший вы наш",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    )
                ]
            ) 
        ]
    )

    ozon_delivery = DeliveryService(
        name=LocalizedString(data={
            "ru":"Ozon Доставка",
            "en":"Ozon Delivery"
            }
        ),
        price=LocalizedPrice(data={
            "RUB": 200,
            "USD": 3
            }
        ),
        requirements_options=[
            DeliveryRequirementsList(
                name=LocalizedString(data={
                    "ru":"По номеру телефона и адресу ПВЗ",
                    "en":""
                    }
                ),
                description=LocalizedString(data={
                    "ru":"описание чего-то там не знаю чего",
                    "en":"сначала на русском текст нормально надо"
                    }
                ),
                requirements=[
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"Номер телефона",
                            "en":"Phone number"
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"пишите номер в формате +7xxxxxxxxxx",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    ),
                    DeliveryRequirement(
                        name=LocalizedString(data={
                            "ru":"Полный адрес пункта выдачи",
                            "en":""
                            }
                        ),
                        description=LocalizedString(data={
                            "ru":"При написании адреса не забудьте перепроверить все ишак дражайший вы наш",
                            "en":"на русском сначала блин давай"
                            }
                        )
                    )
                ]
            ) 
        ]
    )


    # await ctx.db.delivery_services.save(service)
    # await ctx.db.delivery_services.save(cdek)
    # await ctx.db.delivery_services.save(boxberry)
    # await ctx.db.delivery_services.save(ya_delivery)
    # await ctx.db.delivery_services.save(ozon_delivery)

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
        price=LocalizedPrice(data={"RUB": 400, "USD": 10}),
        disallowed_products=[]
    )
    await db.additionals.save(additional)

    print(await db.additionals.get("dildos", PydanticObjectId("681fc67be2f9eecf62c8a750")))