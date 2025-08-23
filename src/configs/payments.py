from schemas.payment_models import PaymentMethod, PaymentMethodsRepository
from schemas.types import LocalizedString

SUPPORTED_PAYMENT_METHODS = PaymentMethodsRepository({
    "manual_sbp": PaymentMethod(
        name=LocalizedString(data={
            "ru": "СБП по номеру телефона",
            "en": "SBP by phone number"
        }),
        description=LocalizedString(data={
            "ru": "Тут надо указать реквизиты для проведения оплаты, и что-то типо \"Если вы хотите выбрать данный платежный метод, произведите по нему оплату и нажмите на кнопку такую-то.\"",
            "en": "DESCRIPTION PLACEHOLDER"
        }),
        enabled=True,
        can_register_receipts=True,
        manual=True
    ),
    "manual_card": PaymentMethod(
        name=LocalizedString(data={
            "ru": "По номеру карты",
            "en": "By card number"
        }),
        description=LocalizedString(data={
            "ru": "Тут надо указать реквизиты для проведения оплаты, и что-то типо \"Если вы хотите выбрать данный платежный метод, произведите по нему оплату и нажмите на кнопку такую-то.\"",
            "en": "DESCRIPTION PLACEHOLDER"
        }),
        enabled=True,
        can_register_receipts=True,
        manual=True
    ),
    "manual_paypal": PaymentMethod(
        name=LocalizedString(data={
            "ru": "PayPal",
            "en": "PayPal"
        }),
        description=LocalizedString(data={
            "ru": "Тут надо указать реквизиты для проведения оплаты, и что-то типо \"Если вы хотите выбрать данный платежный метод, произведите по нему оплату и нажмите на кнопку такую-то.\"",
            "en": "DESCRIPTION PLACEHOLDER"
        }),
        enabled=True,
        can_register_receipts=False,
        manual=True
    ),
})