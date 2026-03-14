from enum import Enum

class LogType(str, Enum):
    personal_data = "personal_data"

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
    
class GiveawayCheckResult(str, Enum):
    ok = "ok"
    giveaway_ended = "giveaway_ended"
    already_in = "already_in"
    error = "error"

class PromocodeCheckResult(str, Enum):
    ok = "ok"
    only_newbies = "only_newbies"
    max_usages_reached = "max_usages_reached"
    no_matching_choices = "no_matching_choices"
    expired = "expired"
    error = "error"
    
class CartItemSource(str, Enum):
    product = "product"
    discounted = "discounted"

class OrderStateKey(str, Enum):
    forming = "forming"
    waiting_for_price_confirmation = "waiting_for_price_confirmation"
    waiting_for_forming = "waiting_for_forming"
    
    waiting_for_payment = "waiting_for_payment"
    waiting_for_manual_payment_confirm = "waiting_for_manual_payment_confirm"
    
    accepted = "accepted"
    
    assembled_waiting_for_send = "assembled_waiting_for_send"
    
    sent = "sent"
    arrived_at_delivery_point = "arrived_at_delivery_point"
    
    received = "received"

__all__ = [
    "MediaType",
    "DiscountType",
    "InviterType",
    "GiveawayCheckResult",
    "PromocodeCheckResult",
    "CartItemSource",
    "OrderStateKey"
]