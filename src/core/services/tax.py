from os import getenv
from schemas.db_models import CartEntry, Order
from schemas.types import Money

from MoyNalogAPI import AsyncMoyNalog
from MoyNalogAPI.schemas import Client, Service

import asyncio
from datetime import datetime


class TaxSystem:
    def __init__(self):
        folder = getenv("CONFIGS_PATH")
        self.client = AsyncMoyNalog(folder)

    async def safe_create_invoice(self, *args, retries: int = 3, timeout: int = 10, **kwargs):
        last_exc = None
        for attempt in range(retries):
            try:
                return await asyncio.wait_for(
                    self.client.create_invoice(*args, **kwargs),
                    timeout=timeout
                )
            except (asyncio.TimeoutError, Exception) as e:
                last_exc = e
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)  # экспоненциальная задержка
                    continue
                raise last_exc

    def distribute_discounts(self, cart_entries: list["CartEntry"], total_discount: "Money") -> list["Money"]:
        from schemas.types import LocalizedMoney, Money
        entry_prices = [
            (entry.configuration.price + entry.frozen_product.price) * entry.quantity
            for entry in cart_entries
        ]

        total_price = sum(entry_prices, LocalizedMoney())

        if total_price.get_amount(total_discount.currency) == 0:
            return [Money(currency=total_discount.currency, amount=0.0) for _ in cart_entries]

        discounts = []
        remaining_discount = total_discount.amount

        for price in entry_prices[:-1]:
            fraction = price.get_amount(total_discount.currency) / total_price.get_amount(total_discount.currency)
            discount_amount = fraction * total_discount.amount
            discount_amount = min(discount_amount, price.get_amount(total_discount.currency))
            
            discounts.append(Money(currency=total_discount.currency, amount=discount_amount))
            remaining_discount -= discount_amount

        last_discount = min(remaining_discount, entry_prices[-1].get_amount(total_discount.currency))
        
        discounts.append(Money(currency=total_discount.currency, amount=last_discount))

        return discounts

    async def invoice_by_order(self, cart_entries: list["CartEntry"], order: "Order", operation_time: datetime) -> str | list[str]:
        from schemas.types import Money
        price_details = order.price_details

        services = []
        client_data = Client()

        discounts = (price_details.bonuses_applied or Money(currency=price_details.products_price.currency, amount=0.0)) + (price_details.promocode_discount or Money(currency=price_details.products_price.currency, amount=0.0))
        entry_discounts = self.distribute_discounts(cart_entries, discounts)

        entries_list = []

        for i, entry in enumerate(cart_entries):
            total_price_per_item = entry.configuration.price.get_amount(discounts.currency) + entry.frozen_product.price.get_amount(discounts.currency)
            remaining_quantity = entry.quantity
            discount_per_item = entry_discounts[i].amount / entry.quantity if entry.quantity else 0

            while remaining_quantity > 0:
                chunk_quantity = min(remaining_quantity, 6)
                chunk_price = total_price_per_item * chunk_quantity - discount_per_item * chunk_quantity
                entries_list.append([
                    f"{entry.frozen_product.name_for_tax}",
                    chunk_price,
                    chunk_quantity
                ])
                remaining_quantity -= chunk_quantity

        for name, price, quantity in entries_list:
            if price > 0.001: services.append(Service(name=name, amount=float(price), quantity=quantity))

        if len(services) == 0: return None
        
        
        if len(services) > 6:
            chunks = [services[i:i + 6] for i in range(0, len(services), 6)]
            receipts = []
            for services_chunk in chunks:

                receipts.append(await self.safe_create_invoice(
                    operation_time=operation_time,
                    svs=services_chunk,
                    client=client_data,
                    payment_type="WIRE",
                    return_receipt_url=True
                ))
            return receipts

        return await self.safe_create_invoice(
            operation_time=operation_time,
            svs=services,
            client=client_data,
            payment_type="WIRE",
            return_receipt_url=True
        )

    async def close(self):
        await self.client.close()