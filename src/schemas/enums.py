from enum import Enum

class PromocodeActionType(str, Enum):
    fixed = "fixed"      # фиксированная сумма
    percent = "percent"  # процент от суммы

class PromocodeCheckResult(str, Enum):
    ok = "ok"
    only_newbies = "only_newbies"
    max_usages_reached = "max_usages_reached"
    expired = "expired"
    error = "error"

class OrderState(str, Enum):
    forming = "forming"
    waiting_for_payment = "waiting_for_payment"
    waiting_for_payment_confirm = "waiting_for_payment_confirm"
    sended = "sended"
    received = "received"