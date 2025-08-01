
from schemas.payment_models import PaymentMethod, PaymentMethodsRepository
from schemas.types import LocalizedString


SUPPORTED_CURRENCIES = {
    "USD": "$",
    "RUB": "₽"
    # "EUR": "€",
    # "BTC": "₿"
    # во прикол
}

SUPPORTED_LANGUAGES_TEXT = {
    "🇷🇺Русский": "ru",
    "🇺🇸English": "en"
}

SUPPORTED_PAYMENT_METHODS = PaymentMethodsRepository({
    "manual_sbp": PaymentMethod(
        name=LocalizedString({
            "ru": "СБП по номеру телефона",
            "en": "SBP by phone number"
        }),
        description=LocalizedString({
            "ru": "Тут надо указать реквизиты для проведения оплаты, и что-то типо \"Если вы хотите выбрать данный платежный метод, произведите по нему оплату и нажмите на кнопку такую-то.\"",
            "en": "DESCRIPTION PLACEHOLDER"
        }),
        enabled=True,
        can_register_receipts=True,
        manual=True
    ),
    "manual_card": PaymentMethod(
        name=LocalizedString({
            "ru": "По номеру карты",
            "en": "By card number"
        }),
        description=LocalizedString({
            "ru": "Тут надо указать реквизиты для проведения оплаты, и что-то типо \"Если вы хотите выбрать данный платежный метод, произведите по нему оплату и нажмите на кнопку такую-то.\"",
            "en": "DESCRIPTION PLACEHOLDER"
        }),
        enabled=True,
        can_register_receipts=True,
        manual=True
    ),
    "manual_paypal": PaymentMethod(
        name=LocalizedString({
            "ru": "PayPal",
            "en": "PayPal"
        }),
        description=LocalizedString({
            "ru": "Тут надо указать реквизиты для проведения оплаты, и что-то типо \"Если вы хотите выбрать данный платежный метод, произведите по нему оплату и нажмите на кнопку такую-то.\"",
            "en": "DESCRIPTION PLACEHOLDER"
        }),
        enabled=True,
        can_register_receipts=False,
        manual=True
    ),
})