from enum import Enum

class MediaType(str, Enum):
    photo = "photo"
    video = "video"
    document = "document"

class DiscountType(str, Enum):
    fixed = "fixed"      # фиксированная сумма
    percent = "percent"  # процент от суммы

class InviterType(str, Enum):
    customer = "user"
    channel = "channel"

class PromocodeCheckResult(str, Enum):
    ok = "ok"
    only_newbies = "only_newbies"
    max_usages_reached = "max_usages_reached"
    expired = "expired"
    error = "error"

class OrderStateKey(str, Enum):
    forming = "forming"
    waiting_for_price_confirmation = "waiting_for_price_confirmation"
    waiting_for_forming = "waiting_for_forming"
    
    waiting_for_payment = "waiting_for_payment"
    waiting_for_manual_payment_confirm = "waiting_for_manual_payment_confirm"
    
    accepted = "accepted"
    
    waiting_for_photo = "waiting_for_photo"
    
    assembled_waiting_for_send = "assembled_waiting_for_send"
    
    sent = "sent"
    received = "received"

__all__ = [
    "MediaType",
    "DiscountType",
    "InviterType",
    "PromocodeCheckResult",
    "OrderStateKey"
]