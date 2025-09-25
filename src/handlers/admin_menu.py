import asyncio
import datetime
import json
import re

from aiogram import Router
from aiogram.filters import CommandObject, Command
from aiogram.types import BufferedInputFile
from pydantic import ValidationError
from pydantic_mongo import PydanticObjectId

from configs.supported import SUPPORTED_LANGUAGES_TEXT
from core.services.db import *

from core.helper_classes import Context
from core.middlewares import RoleCheckMiddleware
from core.states import AdminStates, CommonStates, call_state_handler
from schemas.enums import DiscountType, OrderStateKey
from schemas.types import Discount, LocalizedMoney, LocalizedString
from ui.message_tools import list_commands, split_message
from ui.texts import AdminTextGen

router = Router(name="admin_menu")
middleware = RoleCheckMiddleware("admin")

router.message.middleware.register(middleware)
router.callback_query.middleware.register(middleware)



@router.message(Command("menu"))
async def menu_handler(_, ctx: Context):
    await call_state_handler(AdminStates.Main.Menu, ctx)

@router.message(AdminStates.Main.Menu)
async def menu_handler(_, ctx: Context):
    text = ctx.message.text
    if text == "Покупатели":
        ...
    elif text == "Товары":
        ...
    elif text == "Заказы":
        ...
    elif text == "Промокоды": 
        await call_state_handler(AdminStates.Main.Promocodes, ctx)
    elif text == "Глобальные Плейсхолдеры": 
        await call_state_handler(AdminStates.Main.GlobalPlaceholders, ctx)
    else:
        await call_state_handler(AdminStates.Main.Menu, ctx)
        
@router.message(AdminStates.Main.Promocodes)
async def promocodes_handler(_, ctx: Context):
    text = ctx.message.text
    if text == ctx.t.UncategorizedTranslates.back:
        await call_state_handler(AdminStates.Main.Menu, ctx)
        return
    
    if text == "Создать":
        await call_state_handler(AdminStates.Main.PromocodeCreating, ctx)
    elif text == "Список всех":
        txt = await AdminTextGen.all_promocodes_text(ctx)
        if txt == "":
            await call_state_handler(AdminStates.Main.Promocodes, ctx, send_before="Промокодов нема.")
            return
        
        parts = split_message(txt, limit=4096)
        
        for i, part in enumerate(parts):
            is_last = i == len(parts) - 1
            
            await ctx.message.answer(part)
            if not is_last: await asyncio.sleep(.3)
            
        await call_state_handler(AdminStates.Main.Promocodes, ctx)
    else:
        await call_state_handler(AdminStates.Main.Promocodes, ctx)

@router.message(AdminStates.Main.PromocodeCreating)
async def create_promocode_code_handler(_, ctx: Context):
    text = ctx.message.text
    
    if text == ctx.t.UncategorizedTranslates.cancel:
        await call_state_handler(AdminStates.Main.Promocodes, ctx)
        return

    def parse_localized_string(block: str) -> LocalizedString:
        result = {}
        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            if ":" in line:
                lang, text = line.split(":", 1)
                result[lang.strip()] = text.strip()
        return LocalizedString.from_keys(**result)

    def parse_localized_money(text: str) -> LocalizedMoney:
        result = {}
        for part in re.split(r"[;\n]+", text):
            part = part.strip()
            if not part:
                continue
            cur, amt = part.split(":", 1)
            result[cur.strip().upper()] = float(amt.replace(",", "."))
        return LocalizedMoney.from_dict(result)

    def parse_expire(text: str) -> Optional[datetime.datetime]:
        t = text.strip().lower()
        if t in ("none", "never"):
            return None
        if t.endswith("d"):
            days = int(t[:-1])
            return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)
        return datetime.datetime.strptime(t, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)

    fields = {}
    key = None
    buf = []
    for line in text.splitlines():
        if ":" in line and not line.startswith(" "):
            # новая ключ-строка
            if key:
                # сохраняем предыдущий буфер
                fields[key] = "\n".join(buf).strip()
            key, val = line.split(":", 1)
            key, val = key.strip().lower(), val.strip()
            buf = [val] if val else []  # если сразу есть значение — кладём в буфер
        else:
            # продолжение блока (многострочный)
            if key is not None:
                buf.append(line)
    # сохраняем последний блок
    if key:
        fields[key] = "\n".join(buf).strip()
    
    result = {
        "code": fields["код"],
        "type": fields["тип"].lower(),
        "only_newbies": fields.get("только_новички", "no").lower() in ("yes", "true", "да"),
        "max_usages": -1 if fields.get("макс_использований", "-1").lower() in ("none", "-1") else int(fields["макс_использований"]),
        "expire_date": parse_expire(fields.get("expire", "none")),
    }
    if result["type"] == "percent":
        result["value"] = float(fields["значение"])
    else:
        result["value"] = parse_localized_money(fields["значение"])
    result["description"] = parse_localized_string(fields["описание"])
    
    try:
        promocode = Promocode(
            code=result["code"],
            discount=Discount(
                dicount_type=getattr(DiscountType, result["type"]),
                value=result["value"]
            ),
            description=result["description"],
            only_newbies=result["only_newbies"],
            max_usages=result["max_usages"],
            expire_date=result["expire_date"]
        )
        
        await ctx.services.db.promocodes.save(promocode)
        await call_state_handler(AdminStates.Main.Promocodes, ctx, send_before="Промокод создан.")
        
    except Exception as e:
        raise Exception(f"Не удалось создать промокод: {e}")

@router.message(AdminStates.Main.GlobalPlaceholders)
async def global_placeholders_handler(_, ctx: Context):
    text = ctx.message.text
    if text == ctx.t.UncategorizedTranslates.back:
        await call_state_handler(AdminStates.Main.Menu, ctx)
        return
    
    if text == "Создать": 
        await call_state_handler(AdminStates.Main.GlobalPlaceholdersCreatingKey, ctx)
    elif text == "Список всех":
        txt = await AdminTextGen.all_placeholders_text(ctx)
        if txt == "":
            await call_state_handler(AdminStates.Main.Promocodes, ctx, send_before="Плейсхолдеров нема.")
            return
        
        parts = split_message(txt, limit=4096)
        
        for i, part in enumerate(parts):
            is_last = i == len(parts) - 1
            
            await ctx.message.answer(part)
            if not is_last: await asyncio.sleep(.3)
            
        await call_state_handler(AdminStates.Main.GlobalPlaceholders, ctx)
    elif text == "Изменить": 
        await call_state_handler(AdminStates.Main.GlobalPlaceholdersEditKey, ctx)
    else:
        await call_state_handler(AdminStates.Main.GlobalPlaceholders, ctx)
        return
    
@router.message(AdminStates.Main.GlobalPlaceholdersCreatingKey)
async def global_placeholders_creating_handler(_, ctx: Context):
    text = ctx.message.text
    if text == ctx.t.UncategorizedTranslates.cancel:
        await call_state_handler(AdminStates.Main.GlobalPlaceholders, ctx)
        return
    
    await ctx.fsm.update_data(key=text, **{lang: None for lang in SUPPORTED_LANGUAGES_TEXT.values()})
    await call_state_handler(AdminStates.Main.GlobalPlaceholdersCreatingLangs, ctx)

@router.message(AdminStates.Main.GlobalPlaceholdersCreatingLangs)
async def global_placeholders_creating_langs_handler(_, ctx: Context):
    text = ctx.message.text
    if text == ctx.t.UncategorizedTranslates.cancel:
        await call_state_handler(AdminStates.Main.GlobalPlaceholders, ctx)
        return
    
    remaining_langs = [lang for lang in SUPPORTED_LANGUAGES_TEXT.values() 
                      if not await ctx.fsm.get_value(lang)]
    
    if remaining_langs:
        await ctx.fsm.update_data(**{remaining_langs[0]: text})
        
        if len(remaining_langs) > 1:
            await call_state_handler(AdminStates.Main.GlobalPlaceholdersCreatingLangs, ctx)
            return
    
    langs_dict = {lang: await ctx.fsm.get_value(lang) for lang in SUPPORTED_LANGUAGES_TEXT.values()}
    
    try:
        placeholder = Placeholder(
            key=await ctx.fsm.get_value("key"),
            value=LocalizedString.from_keys(**langs_dict)
        )
        await ctx.services.db.placeholders.save(placeholder)
        await call_state_handler(AdminStates.Main.GlobalPlaceholders, ctx, send_before="Плейсхолдер создан.")
        
    except Exception as e:
        raise Exception(f"Не удалось создать плейсхолдер: {e}")


@router.message(AdminStates.Main.GlobalPlaceholdersEditKey)
async def global_placeholders_edit_request_key_handler(_, ctx: Context):
    text = ctx.message.text
    if text == ctx.t.UncategorizedTranslates.cancel:
        await call_state_handler(AdminStates.Main.GlobalPlaceholders, ctx)
        return
    
    placeholder = await ctx.services.db.placeholders.find_by_key(text)
    
    if not placeholder:
        await call_state_handler(AdminStates.Main.GlobalPlaceholders, ctx, send_before="Плейсхолдер не найден.")
        return

    await ctx.fsm.update_data(key=text, **{lang: None for lang in SUPPORTED_LANGUAGES_TEXT.values()})
    await call_state_handler(AdminStates.Main.GlobalPlaceholdersEditLangs, ctx, placeholder=placeholder)
    
@router.message(AdminStates.Main.GlobalPlaceholdersEditLangs)
async def global_placeholders_edit_langs_handler(_, ctx: Context):
    text = ctx.message.text
    if text == ctx.t.UncategorizedTranslates.cancel:
        await call_state_handler(AdminStates.Main.GlobalPlaceholders, ctx)
        return
    
    remaining_langs = [lang for lang in SUPPORTED_LANGUAGES_TEXT.values() 
                      if not await ctx.fsm.get_value(lang)]
    
    placeholder = await ctx.services.db.placeholders.find_by_key(await ctx.fsm.get_value("key"))

    if not placeholder:
        await call_state_handler(AdminStates.Main.GlobalPlaceholders, ctx, send_before="Плейсхолдер не найден.")
        return
    
    if remaining_langs:
        await ctx.fsm.update_data(**{remaining_langs[0]: text})
        
        if len(remaining_langs) > 1:
            await call_state_handler(AdminStates.Main.GlobalPlaceholdersEditLangs, ctx, placeholder=placeholder)
            return
    
    langs_dict = {lang: await ctx.fsm.get_value(lang) for lang in SUPPORTED_LANGUAGES_TEXT.values()}
    
    try:
        placeholder.value = LocalizedString.from_keys(**langs_dict)
        await ctx.services.db.placeholders.save(placeholder)
        await call_state_handler(AdminStates.Main.GlobalPlaceholders, ctx, send_before="Плейсхолдер изменен.")
        
    except Exception as e:
        raise Exception(f"Не удалось изменить плейсхолдер: {e}")
