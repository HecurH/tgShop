import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any, Iterable, List, Optional, Tuple, Union
from aiogram import Bot
from aiogram.types import ReplyMarkupUnion, InputFile, URLInputFile, Message
from aiogram.exceptions import TelegramRetryAfter, TelegramAPIError, TelegramBadRequest
from aiogram.utils.media_group import MediaGroupBuilder
from core.types.enums import CartItemSource
from schemas.db_models import Customer, DeliveryService, Order
from core.types.values import SavedTMessage
from core.types.values import Money
from ui.keyboards import UncategorizedKBs

from core.helper_classes import Context, MessageWrapper
from ui.message_tools import build_list, split_message
from ui.texts import gen_product_configurable_info_text
from ui.translates import NotificatorTranslates

MediaItem = Tuple[str, Union[InputFile, URLInputFile]]

@dataclass
class NotificatorConfig:
    retry_attempts: int = 4
    base_backoff: float = 0.5
    between_messages_delay: float = 0.4
    use_queue: bool = True
    queue_workers: int = 1

class TelegramNotificator:
    def __init__(self, bot: Bot, default_chat_id: Optional[int] = None,
                 config: NotificatorConfig = NotificatorConfig()):
        self.bot = bot
        self.default_chat_id = default_chat_id
        self.config = config
        self.logger = logging.getLogger(__name__)

        self._queue: Optional[asyncio.Queue] = asyncio.Queue() if config.use_queue else None
        self._workers: List[asyncio.Task] = []
        if self._queue:
            for _ in range(config.queue_workers):
                self._workers.append(asyncio.create_task(self._worker_loop()))

    async def _worker_loop(self):
        while True:
            job = await self._queue.get()
            try:
                job_type = job.pop("type", "notification")
                if job_type == "forward":
                    await self._send_forward_internal(**job)
                else:
                    await self._send_notification_internal(**job)
            except Exception as e:
                self.logger.exception("Failed sending notification from queue: %s", e)
            finally:
                self._queue.task_done()

    async def stop_workers(self):
        if self._queue:
            await self._queue.join()
            for w in self._workers:
                w.cancel()
            await asyncio.gather(*self._workers, return_exceptions=True)

    async def send_notification(self,
                                message: str,
                                chat_id: Optional[int] = None,
                                reply_markup: Optional[ReplyMarkupUnion] = None,
                                media: Optional[Union[InputFile, URLInputFile, List[MediaItem]]] = None,
                                media_type: str = "photo",
                                use_queue: Optional[bool] = None,
                                **kwargs: Any):
        target = chat_id or self.default_chat_id
        if not target:
            raise ValueError("No chat_id provided and no default configured")

        job = dict(message=message, chat_id=target, reply_markup=reply_markup,
                   media=media, media_type=media_type, kwargs=kwargs)
        if (use_queue if use_queue is not None else self.config.use_queue) and self._queue is not None:
            await self._queue.put(job)
            return

        await self._send_notification_internal(**job)
        
    async def send_forwarded_notification(self,
                                          message: Union[Message, SavedTMessage, List[Message | SavedTMessage]],
                                          chat_id: Optional[int] = None,
                                          as_copy: bool = True,
                                          use_queue: Optional[bool] = None,
                                          **kwargs: Any):
        target = chat_id or self.default_chat_id
        if not target:
            raise ValueError("No chat_id provided and no default configured")

        # нормализуем в список
        msgs = message if isinstance(message, list) else [message]

        job = dict(type="forward", messages=msgs, chat_id=target, as_copy=as_copy, kwargs=kwargs)
        if (use_queue if use_queue is not None else self.config.use_queue) and self._queue is not None:
            await self._queue.put(job)
            return

        await self._send_forward_internal(**job)

    async def _send_notification_internal(self, message, chat_id, reply_markup, media, media_type, kwargs):
        attempt = 0
        while True:
            try:
                await self._send(chat_id, message, reply_markup, media, media_type)
                self.logger.debug("Sent message to chat_id=%s", chat_id)
                return
            except TelegramRetryAfter as e:
                attempt += 1
                wait = max(self.config.base_backoff * (2 ** (attempt - 1)), getattr(e, "retry_after", 0))
                self.logger.warning("RetryAfter for chat %s, sleeping %s s (attempt %s)", chat_id, wait, attempt)
                await asyncio.sleep(wait)
                if attempt >= self.config.retry_attempts:
                    raise
            except (TelegramAPIError, TelegramBadRequest):
                attempt += 1
                self.logger.exception("Telegram API error while sending to %s (attempt %s)", chat_id, attempt)
                if attempt >= self.config.retry_attempts:
                    raise
                await asyncio.sleep(self.config.base_backoff * (2 ** (attempt - 1)))
            except Exception:
                self.logger.exception("Unexpected exception sending notification")
                raise
            
    async def _send_forward_internal(self, messages: List[Message | SavedTMessage], chat_id: int, as_copy: bool, kwargs: dict):
        attempt = 0
        while True:
            try:
                await self._forward(messages=messages, chat_id=chat_id, as_copy=as_copy)
                self.logger.debug("Forwarded %s messages to chat_id=%s", len(messages), chat_id)
                return
            except TelegramRetryAfter as e:
                attempt += 1
                wait = max(self.config.base_backoff * (2 ** (attempt - 1)), getattr(e, "retry_after", 0))
                self.logger.warning("RetryAfter for forward to chat %s, sleeping %s s (attempt %s)", chat_id, wait, attempt)
                await asyncio.sleep(wait)
                if attempt >= self.config.retry_attempts:
                    raise
            except (TelegramAPIError, TelegramBadRequest) as e:
                attempt += 1
                self.logger.exception("Telegram API error while forwarding to %s (attempt %s)", chat_id, attempt)
                if attempt >= self.config.retry_attempts:
                    raise
                await asyncio.sleep(self.config.base_backoff * (2 ** (attempt - 1)))
            except Exception:
                self.logger.exception("Unexpected exception forwarding notification")
                raise

    async def _send(self, chat_id: int, message: str, reply_markup, media, media_type: str):
        parts = split_message(message, limit=4096)
        for i, part in enumerate(parts):
            is_first = i == 0
            is_last = i == len(parts) - 1

            if is_first and media:
                if isinstance(media, list):
                    album_builder = MediaGroupBuilder()
                    for t, m in media:
                        album_builder.add(type=t, media=m)
                    await self.bot.send_media_group(chat_id=chat_id, media=album_builder.build())
                    
                    await asyncio.sleep(0.15)
                    await self.bot.send_message(chat_id=chat_id, text=part,
                                                reply_markup=reply_markup if is_last else None,
                                                disable_web_page_preview=True)
                elif media_type == "photo":
                    await self.bot.send_photo(chat_id=chat_id, photo=media, caption=part,
                                              reply_markup=reply_markup if is_last else None)
                elif media_type == "video":
                    await self.bot.send_video(chat_id=chat_id, video=media, caption=part,
                                              reply_markup=reply_markup if is_last else None)
            else:
                await self.bot.send_message(chat_id=chat_id, text=part,
                                           reply_markup=reply_markup if is_last else None,
                                           disable_web_page_preview=True)
            if not is_last:
                await asyncio.sleep(self.config.between_messages_delay)
                
    async def _forward(self, messages: List[Message | SavedTMessage], chat_id: int, as_copy: bool):
        for i, msg in enumerate(messages):
            if isinstance(msg, Message) or isinstance(msg, MessageWrapper):
                if not hasattr(msg, "chat") or not hasattr(msg, "message_id"):
                    self.logger.warning("Skipping non-Message element in forward list: %r", msg)
                    continue
            elif not isinstance(msg, SavedTMessage):
                self.logger.warning("Skipping non-Message element in forward list: %r", msg)
                continue


            from_chat_id = msg.chat.id if isinstance(msg, Message) or isinstance(msg, MessageWrapper) else msg.chat_id
            message_id = msg.message_id

            if as_copy:
                # копия — от имени бота
                await self.bot.copy_message(chat_id=chat_id, from_chat_id=from_chat_id, message_id=message_id)
            else:
                # обычная пересылка — сохраняется оригинальный отправитель
                await self.bot.forward_message(chat_id=chat_id, from_chat_id=from_chat_id, message_id=message_id)

            # небольшая пауза между сообщениями, чтобы сохранить порядок/альбомы
            if i != len(messages) - 1:
                await asyncio.sleep(self.config.between_messages_delay)

class TelegramChannelLogsNotificator:
    def __init__(self, notificator: TelegramNotificator):
        self.notificator = notificator
    
    async def send_error(self, ctx: Context, error: str):
        try:
            user_info = f"Пользователь {ctx.customer.id}, Состояние: {await ctx.fsm.get_state()}\n\n" if ctx.customer else ""
            await self.notificator.send_notification(f"{user_info}{str(error)}")
        except Exception as e:
            logging.getLogger(__name__).critical(f"Не удалось отправить ошибку в канал логов: {e}")

class AdminChatNotificator:
    def __init__(self, notificator: TelegramNotificator):
        self.notificator = notificator
        
    async def send_price_confirmation(self, order: Order, ctx: Context):
        text = f"<a href=\"tg://user?id={ctx.customer.user_id}\">Пользователь</a> собрал корзину и отправил ее на подтверждение.\nБазовая стоимость без наценки за сложность: {order.price_details.products_price.to_text()}\n\n<b>Содержимое заказа:</b>\n"
        ctx.lang = "ru"

        entries = await ctx.services.db.cart_entries.find_entries_by_order(order)
        products_dict = {entry.frozen_snapshot.id: entry.frozen_snapshot for entry in entries if entry.source_type == CartItemSource.product}

        for idx, entry in enumerate(entries):
            if entry.source_type == CartItemSource.product and (product := products_dict.get(entry.source_id)):
                amount_price = f"{entry.quantity} шт. — {entry.calculate_price(product).to_text('RUB')}" if entry.quantity > 1 else entry.calculate_price(product).to_text('RUB')
                
                text += f"{idx+1}: {product.name.get('ru')} ({amount_price}):\n{gen_product_configurable_info_text(entry.configuration, ctx)}\n\n"
            elif entry.source_type == CartItemSource.discounted:
                text += f"{idx+1}: {entry.frozen_snapshot.name.get('ru')} ({entry.calculate_price().to_text('RUB')}):\n{entry.frozen_snapshot.description.get('ru')}\n\n"
                
        text += f"\n\n<code>/msg_to {ctx.customer.user_id}</code>\n\n<code>/unform_order {order.id}</code>\n\n<code>/confirm_order_price {order.id}</code>"

        await self.notificator.send_notification(text, reply_markup=await UncategorizedKBs.go_to_bot(ctx))
            
    async def send_payment_confirmation(self, order: Order, ctx: Context):
        payment_method = order.payment_method
        text = f"<a href=\"tg://user?id={ctx.customer.user_id}\">Пользователь</a> сообщил о ручной оплате заказа на сумму {order.price_details.total_price.to_text()};\nСпособ оплаты: {payment_method.name.get('ru') if payment_method else 'Неизвестно'}."
        text += "\nСодержимое заказа:\n"
        
        ctx.lang = "ru"

        entries = await ctx.services.db.cart_entries.find_entries_by_order(order)
        products_dict = {entry.frozen_snapshot.id: entry.frozen_snapshot for entry in entries if entry.source_type == CartItemSource.product}

        for idx, entry in enumerate(entries):
            if entry.source_type == CartItemSource.product and (product := products_dict.get(entry.source_id)):
                amount_price = f"{entry.quantity} шт. — {entry.calculate_price(product).to_text('RUB')}" if entry.quantity > 1 else entry.calculate_price(product).to_text('RUB')
                
                text += f"  {idx+1} - {product.name.get('ru')} ({amount_price}):\n{gen_product_configurable_info_text(entry.configuration, ctx)}\n\n"
            elif entry.source_type == CartItemSource.discounted:
                text += f"  {idx+1}: {entry.frozen_snapshot.name.get('ru')} ({entry.calculate_price().to_text('RUB')}):\n{entry.frozen_snapshot.description.get('ru')}\n\n"
                
        text += f"\nЭто первый заказ пользователя, не забудь вложить пробник!\n" if await ctx.services.db.orders.count_formed_customer_orders(ctx.customer) == 1 else "\n\n"
        
        text += f"<code>/confirm_manual_payment {order.id}|{datetime.now(timezone.utc)}</code>\n\n<code>/unform_order {order.id}</code>\n\n<code>/msg_to {ctx.customer.user_id}</code>"

        await self.notificator.send_notification(text, reply_markup=await UncategorizedKBs.go_to_bot(ctx))
        
    async def send_delivery_manual_price_confirmation(self, service: DeliveryService, ctx: Context):
        
        delivery_requirements_info = build_list([f"{requirement.name.get(ctx)} - <tg-spoiler>{requirement.value.get()}</tg-spoiler>" for requirement in service.selected_option.requirements],
                                                padding=2)
        
        await self.notificator.send_notification(f"<a href=\"tg://user?id={ctx.customer.user_id}\">Пользователь</a> запросил ручное подтверждение стоимости доставки.\n\n{delivery_requirements_info}\n\n<code>/manual_delivery_price {ctx.customer.user_id} {service.id} {service.get_selected_option_index()} {service.securs_to_str()} {service.price.model_dump_json()}</code>\n\n<code>/cancel_manual_delivery_price_confirm {ctx.customer.user_id}</code>",
                                                 reply_markup=await UncategorizedKBs.go_to_bot(ctx))
        
class UserTelegramNotificator:
    def __init__(self, notificator: TelegramNotificator):
        self.notificator = notificator
        
    async def forward_admin_message(self, customer: Customer, message: Message):
        if customer.kicked: return
        await self.notificator.send_forwarded_notification(message,
                                                           chat_id=customer.user_id)
        
        await self.notificator.send_notification(NotificatorTranslates.User.admin_message.translate(customer.lang).format(username=message.from_user.username),
                                                 chat_id=customer.user_id)
    
    async def mass_forward_admin_message(self, customers: Iterable[Customer], message: Message):
        
        
        for customer in customers:
            if customer.kicked: continue
            
            await self.notificator.send_forwarded_notification(message,
                                                               chat_id=customer.user_id)
            await asyncio.sleep(0.1)
            await self.notificator.send_notification(NotificatorTranslates.User.admin_message.translate(customer.lang).format(username=message.from_user.username),
                                                     chat_id=customer.user_id)
            await asyncio.sleep(2.4)
        
    
    #-----------
    async def send_delivery_price_confirmed(self, customer: Customer):
        if customer.kicked: return
        await self.notificator.send_notification(NotificatorTranslates.Delivery.delivery_price_confirmed.translate(customer.lang),
                                                 chat_id=customer.user_id)
        
    async def send_delivery_price_rejected(self, customer: Customer):
        if customer.kicked: return
        await self.notificator.send_notification(NotificatorTranslates.Delivery.delivery_price_rejected.translate(customer.lang),
                                                 chat_id=customer.user_id)
        
    async def send_delivery_price_rejected_with_reason(self, customer: Customer, reason: str):
        if customer.kicked: return
        await self.notificator.send_notification(NotificatorTranslates.Delivery.delivery_price_rejected_with_reason.translate(customer.lang).format(reason=reason),
                                                 chat_id=customer.user_id)
    #-----------
    async def send_order_price_confirmed(self, customer: Customer):
        if customer.kicked: return
        await self.notificator.send_notification(NotificatorTranslates.Order.order_price_confirmed.translate(customer.lang),
                                                 chat_id=customer.user_id)
        
    async def send_order_state_changed(self, customer: Customer, order: Order, comment: Optional[SavedTMessage] = None):
        if customer.kicked: return
        if comment:
            await self.notificator.send_forwarded_notification(comment,
                                                               chat_id=customer.user_id)
        
        await self.notificator.send_notification(NotificatorTranslates.Order.order_state_changed.translate(customer.lang).format(order_puid=f"#{order.puid}", order_state=order.state.get_localized_name(customer.lang)),
                                                 chat_id=customer.user_id)
    
    async def send_order_payment_accepted(self, customer: Customer, order: Order, receipt_url: Optional[str | list[str]] = None):
        if customer.kicked: return
        media = ([("photo", URLInputFile(url)) for url in receipt_url] if isinstance(receipt_url, list) else URLInputFile(receipt_url)) if receipt_url else None
        
        await self.notificator.send_notification(NotificatorTranslates.Order.order_payment_accepted.translate(customer.lang).format(order_puid=f"#{order.puid}"),
                                                 chat_id=customer.user_id,
                                                 media=media)
    
    async def send_inviter_reward(self, customer: Customer, reward: Money):
        if customer.kicked: return
        await self.notificator.send_notification(NotificatorTranslates.User.inviter_reward.translate(customer.lang).format(reward=reward.to_text(), balance=customer.bonus_wallet.to_text()),
                                                 chat_id=customer.user_id)
        
    async def send_order_unformed(self, customer: Customer, order: Order):
        if customer.kicked: return
        await self.notificator.send_notification(NotificatorTranslates.Order.order_unformed.translate(customer.lang).format(order_puid=f"#{order.puid}"),
                                                 chat_id=customer.user_id)
    
    async def send_order_unformed_with_reason(self, customer: Customer, order: Order, reason: str):
        if customer.kicked: return
        await self.notificator.send_notification(NotificatorTranslates.Order.order_unformed_with_reason.translate(customer.lang).format(order_puid=f"#{order.puid}", reason=reason),
                                                 chat_id=customer.user_id)
    
    #-----------
    
    async def send_bonus_money_added(self, customer: Customer, money: Money):
        if customer.kicked: return
        await self.notificator.send_notification(NotificatorTranslates.User.bonus_money_added.translate(customer.lang).format(money=money.to_text(), balance=customer.bonus_wallet.to_text()),
                                                 chat_id=customer.user_id)

class NotificatorHub:
    def __init__(self, bot: Bot, logs_channel_id: Optional[int] = None, admin_chat_id: Optional[int] = None, config: NotificatorConfig = NotificatorConfig()):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.config = config

        
        self.TelegramChannelLogs = TelegramChannelLogsNotificator(TelegramNotificator(bot=bot, default_chat_id=logs_channel_id, config=config))
        self.AdminChatNotificator = AdminChatNotificator(TelegramNotificator(bot=bot, default_chat_id=admin_chat_id, config=config))
        
        self.UserTelegramNotificator = UserTelegramNotificator(TelegramNotificator(bot=bot, config=config))
    
    async def stop(self):
        await self.TelegramChannelLogs.notificator.stop_workers()
        await self.AdminChatNotificator.notificator.stop_workers()
        await self.UserTelegramNotificator.notificator.stop_workers()