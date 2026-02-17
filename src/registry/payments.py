from schemas.entities.payment import PaymentMethod, PaymentMethodsRepository
from core.types.values import LocalizedString

SUPPORTED_PAYMENT_METHODS = PaymentMethodsRepository({
    # "manual_sbp": PaymentMethod(
    #     name=LocalizedString(data={
    #         "ru": "СБП по номеру телефона",
    #         "en": "SBP by phone number"
    #     }),
    #     description=LocalizedString(data={
    #         "ru": "Здесь описание метода оплаты, инфа которая мб нужна перед оформлением заказа",
    #         "en": "DESCRIPTION PLACEHOLDER"
    #     }),
    #     currency="RUB",
    #     payment_details=LocalizedString(data={
    #         "ru": "Тут надо указать реквизиты для проведения оплаты, и что-то типо \"Если вы хотите выбрать данный платежный метод, произведите по нему оплату и нажмите на кнопку такую-то.\"",
    #         "en": "PAYMENT DETAILS PLACEHOLDER"
    #     }),
    #     enabled=True,
    #     can_register_receipts=True,
    #     manual=True
    # ),
    "manual_card": PaymentMethod(
        name=LocalizedString(data={
            "ru": "По номеру карты",
            "en": "By card number"
        }),
        description=LocalizedString(data={
            "ru": "Перевод по номеру карты (РФ), возможна комиссия при переводе, уточняйте условия у банка.",
            "en": "Transfer by card number (Russian Federation), a transfer fee is possible, please check the conditions with the bank."
        }),
        currency="RUB",
        payment_details=LocalizedString(data={
            "ru": "Перевод на карту Сбербанка 2202205334616056. (Белан Н. С.)\nПожалуйста, не оставляйте комментариев к переводу и отправляйте точную сумму, спасибо!",
            "en": "Transfer to Sberbank card 2202205334616056. (Белан Н. С.)\nPlease do not leave comments on the transfer and send the exact amount, thank you!"
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
            "ru": "Перевод используя систему PayPal.",
            "en": "Transfer using PayPal system"
        }),
        currency="USD",
        payment_details=LocalizedString(data={
            "ru": "Для оплаты заказов через PayPal, пожалуйста, свяжитесь с @TechnoZmeyka после нажатия на кнопку.",
            "en": "To pay for orders via PayPal, please contact @TechnoZmeyka after clicking the button."
        }),
        enabled=True,
        can_register_receipts=False,
        manual=True
    ),
})

__all__ = ["SUPPORTED_PAYMENT_METHODS"]