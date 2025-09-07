from abc import abstractmethod, ABC
import asyncio
from typing import Optional
from aiogram.types import ReplyMarkupUnion
from schemas.db_models import Customer, Order, DeliveryInfo
from ui.keyboards import AdminKBs

from core.helper_classes import Context
from ui.message_tools import build_list
from ui.texts import gen_product_configurable_info_text
from ui.translates import NotificatorTranslates

class Notificator(ABC):
    @abstractmethod
    async def send_notification(self, **_): ...
    
class TelegramNotificator(Notificator):
    def __init__(self, chat_id: Optional[str] = None):
        self._chat_id = chat_id

    async def send_notification(self, ctx: Context, message: str, reply_markup: Optional[ReplyMarkupUnion] = None, **_):
        await ctx.message.bot.send_message(chat_id=self._chat_id, text=message, reply_markup=reply_markup)
        


class TelegramChannelLogsNotificator(TelegramNotificator):
    def __init__(self, channel_id: str):
        super().__init__(chat_id=channel_id)
    
    async def send_error(self, ctx: Context, error: str):
        user_info = f"User {ctx.customer.id}, State: {await ctx.fsm.get_state()}\n\n" if ctx.customer else ""
        
        await self.send_notification(ctx, f"{user_info}{error}")

class AdminChatNotificator(TelegramNotificator):
    def __init__(self, chat_id: str):
        super().__init__(chat_id=chat_id)
        
    async def send_price_confirmation(self, order: Order, ctx: Context):
        text = f"<a href=\"tg://user?id={ctx.customer.user_id}\">Пользователь</a> собрал корзину и отправил ее на подтверждение.\nБазовая стоимость без наценки за сложность: {order.price_details.products_price.to_text()}\n\n<b>Содержимое заказа:</b>\n"
        ctx.lang = "ru"

        entries = await ctx.db.cart_entries.get_entries_by_order(order)
        products = await ctx.db.products.find_by({"_id": {"$in": [entry.product_id for entry in entries]}})
        products_dict = {product.id: product for product in products}

        for entry in entries:
            if product := products_dict.get(entry.product_id):
                text += f"{product.name.get('ru')}:\n{gen_product_configurable_info_text(entry.configuration, ctx)}\n\n"
                
        text += f"\n\n<code>/admin_msg_to {ctx.customer.user_id}</code>\n\n<code>/admin_unform_order {order.id}</code>\n\n<code>/admin_confirm_order_price {order.id}</code>"

        if len(text) <= 4096:
            await self.send_notification(ctx, text)
        else:
            for part in text.split("\n\n"):
                await self.send_notification(ctx, part)
                await asyncio.sleep(0.3)
            
    
    async def send_payment_confirmation(self, order: Order, ctx: Context):
        payment_method = order.payment_method
        await self.send_notification(ctx, f"<a href=\"tg://user?id={ctx.customer.user_id}\">Пользователь</a> сообщил о ручной оплате заказа на сумму {order.price_details.total_price.to_text()};\nСпособ оплаты: {payment_method.name.get('ru') if payment_method else 'Неизвестно'}."
                                     )
        
    async def send_delivery_manual_price_confirmation(self, delivery_info: DeliveryInfo, ctx: Context):
        
        delivery_requirements_info = build_list([f"{requirement.name.get('ru')} - <tg-spoiler>{requirement.value.get()}</tg-spoiler>" for requirement in delivery_info.service.selected_option.requirements],
                                                padding=2)
        
        await self.send_notification(ctx, f"<a href=\"tg://user?id={ctx.customer.user_id}\">Пользователь</a> запросил ручное подтверждение стоимости доставки.\n\n{delivery_requirements_info}\n\n<code>/manual_delivery_price {ctx.customer.user_id} {delivery_info.service.id} {delivery_info.service.get_selected_option_index()} {delivery_info.service.securs_to_str()} {delivery_info.service.price.model_dump(mode='json')}</code>\n\n<code>/cancel_manual_delivery_price_confirm {ctx.customer.user_id}</code>",
                                     reply_markup=await AdminKBs.Orders.delivery_manual_price_confirmation(ctx)
                                     )
        
class UserTelegramNotificator(TelegramNotificator):
    async def send_delivery_price_confirmed(self, customer: Customer, ctx: Context):
        super().__init__(chat_id=customer.user_id)
        await self.send_notification(ctx, NotificatorTranslates.Delivery.translate("delivery_price_confirmed", customer.lang))
        
    async def send_delivery_price_rejected(self, customer: Customer, ctx: Context):
        super().__init__(chat_id=customer.user_id)
        await self.send_notification(ctx, NotificatorTranslates.Delivery.translate("delivery_price_rejected", customer.lang))
        
    async def send_delivery_price_rejected_with_reason(self, customer: Customer, ctx: Context, reason: str):
        super().__init__(chat_id=customer.user_id)
        await self.send_notification(ctx, NotificatorTranslates.Delivery.translate("delivery_price_rejected_with_reason", customer.lang).format(reason=reason))

        
class NotificatorHub:
    def __init__(self, logs_channel_id, admin_chat_id):
        self.TelegramChannelLogs = TelegramChannelLogsNotificator(logs_channel_id)
        self.AdminChatNotificator = AdminChatNotificator(admin_chat_id)
        self.UserTelegramNotificator = UserTelegramNotificator()