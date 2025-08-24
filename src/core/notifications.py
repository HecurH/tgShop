from abc import abstractmethod, ABC
from typing import Optional
from aiogram.types import ReplyMarkupUnion
from schemas.db_models import Order
from ui.keyboards import AdminKBs

from core.helper_classes import Context

class Notificator(ABC):
    @abstractmethod
    async def send_notification(self, **_): ...
    
class TelegramNotificator(Notificator):
    def __init__(self, chat_id: str):
        self._chat_id = chat_id

    async def send_notification(self, ctx: Context, message: str, reply_markup: Optional[ReplyMarkupUnion] = None, **_):
        await ctx.message.bot.send_message(chat_id=self._chat_id, text=message, reply_markup=reply_markup)
        


class TelegramChannelLogsNotificator(TelegramNotificator):
    def __init__(self, channel_id: str):
        super().__init__(chat_id=channel_id)
    
    async def send_error(self, ctx: Context, error: str):
        user_info = f"User {ctx.customer.id}, State: {await ctx.fsm.get_state()}\n\n" if ctx.customer else ""
        
        await self.send_notification(ctx, f"{user_info}{error}")

class ManualPaymentConfirmationNotificator(TelegramNotificator):
    def __init__(self, chat_id: str):
        super().__init__(chat_id=chat_id)
        
    async def send_payment_confirmation(self, order: Order, ctx: Context):
        payment_method = order.payment_method
        await self.send_notification(ctx, f"<a href=\"tg://user?id={ctx.customer.user_id}\">Пользователь</a> сообщил о ручной оплате заказа на сумму {order.price_details.total_price.to_text()};\nСпособ оплаты: {payment_method.name.get('ru') if payment_method else 'Неизвестно'};",
                                     reply_markup=AdminKBs.Orders.manual_payment_confirmation(ctx, order)
                                     )
        
class NotificatorHub:
    def __init__(self, logs_channel_id, admin_chat_id):
        self.TelegramChannelLogs = TelegramChannelLogsNotificator(logs_channel_id)
        self.ManualPaymentConfirmation = ManualPaymentConfirmationNotificator(admin_chat_id)
        print(f"Logs channel id: {logs_channel_id}, Admin chat id: {admin_chat_id}")