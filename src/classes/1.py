import asyncio
import aiohttp

API_URL = "https://api.exchangerate-api.com/v4/latest/RUB"

async def fetch_rates():
    async with aiohttp.ClientSession() as session:
        async with session.get(API_URL) as response:
            data = await response.json()
            print(f"Курс USD к EUR: {data['rates']['USD']}")

asyncio.run(fetch_rates())
