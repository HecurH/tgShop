import asyncio
import functools
import logging
from datetime import timezone, datetime
from typing import Literal

import aiohttp
from MoyNalogAPI.schemas import Service, Client, ProfileStorage, Incomes, UserProfile

def token_rotation(func):
    @functools.wraps(func)
    async def wrapper(self: "AsyncMoyNalog", *args, **kwargs):
        if hasattr(self.storage, "tokenExpireIn") and self.storage.tokenExpireIn and datetime.now(timezone.utc) < self.storage.tokenExpireIn:
            return await func(self, *args, **kwargs)

        await self._refresh_token()

        return await func(self, *args, **kwargs)

    return wrapper




class AsyncMoyNalog:
    ENDPOINT = "https://lknpd.nalog.ru/api/v1"

    def __init__(self, storage_path: str):
        self._session = None
        self.__logger = logging.getLogger(__name__)
        
        self._storage_path = storage_path
        self.storage: ProfileStorage = ProfileStorage.get(self._storage_path)

        self.__init_session()


    def __init_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self.__logger.debug("MoyNalog aiohttp session created.")

    async def close(self):
        if self._session is not None:
            await self._session.close()
            self._session = None
            self.__logger.debug("MoyNalog aiohttp session closed.")

    def __get_curtime(self):
        local_tz = datetime.now().astimezone().tzinfo
        current_time = datetime.now(local_tz)
        return current_time.replace(microsecond=0).astimezone().isoformat()
    
    async def _refresh_token(self):
        if not self.storage.refreshToken:
            return
        req = {
            "refreshToken": self.storage.refreshToken,
            "deviceInfo": {
                "sourceDeviceId": self.storage.sourceDeviceId,
                "sourceType": "WEB",
                "appVersion": "1.0.0",
                "metaDetails": {
                    "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15"
                }
            }
        }

        url = f"{self.ENDPOINT}/auth/token"
        try:
            async with self._session.post(url, json=req, timeout=5) as response:
                
                json: dict = await response.json()
                
                if response.status != 200:
                    self.__logger.critical(f"MoyNalog refresh_token error: {json}")
                    return
                self.storage.refreshToken = json.get("refreshToken")
                self.storage.token = json.get('token')
                self.storage.save(self._storage_path)
        except asyncio.TimeoutError:
            self.__logger.critical("Timeout: API не ответил вовремя")
            return None

    def get_receipt_url(self, approved_receipt_uuid):
        return f"{self.ENDPOINT}/receipt/{self.storage.profile.get('inn')}/{approved_receipt_uuid}/print"

    @token_rotation
    async def create_invoice(self,
                       operation_time: datetime,
                       svs: list[Service],
                       client: Client,
                       payment_type: Literal["CASH", "WIRE"] = "CASH",
                       ignore_max_total_income_restriction: bool = False,
                       return_receipt_url: bool = False):
        """
        Создает новый чек (invoice) для клиента.

        :param operation_time: Время операции.
        :param svs: Список услуг (объекты Service).
        :param client: Клиент, для которого создается чек (объект Client).
        :param payment_type: Тип оплаты ("CASH" или "CARD").
        :param ignore_max_total_income_restriction: Игнорировать ограничение на максимальный доход (по умолчанию False).
        :param return_receipt_url: Возвращать URL чека (по умолчанию False).
        :return: Ответ от API в формате approvedReceiptUuid или URL чека, если return_receipt_url=True.
        """

        url = f"{self.ENDPOINT}/income"

        # Преобразование услуг в формат для отправки
        services = [el.model_dump() for el in svs]
        totalamount = sum(el.amount * el.quantity for el in svs)

        # Формирование тела запроса
        body = {
            "operationTime": operation_time.replace(microsecond=0).astimezone().isoformat(),
            "requestTime": self.__get_curtime(),
            "services": services,
            "totalAmount": totalamount,
            "client": client.model_dump(),
            "paymentType": payment_type,
            "ignoreMaxTotalIncomeRestriction": ignore_max_total_income_restriction
        }

        try:
            # Отправка POST-запроса на создание чека
            async with self._session.post(url, headers=self.storage.get_auth_headers(), json=body, timeout=5) as response:
                if response.status == 200:
                    json = await response.json()
                    print(json)
                    approved_receipt_uuid = json.get("approvedReceiptUuid")
                    
                    if return_receipt_url:
                        return self.get_receipt_url(approved_receipt_uuid)

                    return approved_receipt_uuid
                else:
                    json = await response.json()
                    self.__logger.critical(json)
                    return None

        except aiohttp.ClientError as e:
            self.__logger.critical(e)
            return None
        except asyncio.TimeoutError:
            self.__logger.critical("Timeout: API не ответил вовремя")
            return None
    
    @token_rotation
    async def cancel_invoice(self,
                       operation_time: datetime,
                       receipt_uuid: str,
                       comment: Literal["CANCEL", "REFUND"] = "CANCEL",
                       partner_code: str = None
                       ) -> bool:

        url = f"{self.ENDPOINT}/cancel"

        # Формирование тела запроса
        body = {
            "operationTime": operation_time.replace(microsecond=0).astimezone().isoformat(),
            "requestTime": self.__get_curtime(),
            "comment": comment,
            "receiptUuid": receipt_uuid,
            "partnerCode": partner_code
        }

        try:
            # Отправка POST-запроса на удаление чека
            async with self._session.post(url, headers=self.storage.get_auth_headers(), json=body, timeout=5) as response:
                if response.status == 200:
                    return True
                json = await response.json()
                self.__logger.critical(json)
                return False

        except aiohttp.ClientError as e:
            self.__logger.critical(e)
            return False
        except asyncio.TimeoutError:
            self.__logger.critical("Timeout: API не ответил вовремя")
            return False
        
    @token_rotation
    async def get_profile(self):
        url = f"{self.ENDPOINT}/user"

        try:
            async with self._session.get(url, headers=self.storage.get_auth_headers(), timeout=5) as response:
                json = await response.json()
                if response.status == 200:
                    return UserProfile(**json)
                self.__logger.critical(json)
                return None
        except asyncio.TimeoutError:
            self.__logger.critical("Timeout: API не ответил вовремя")
            return None

    @token_rotation
    async def get_incomes(self,
                    startDate: datetime = None,
                    endDate: datetime = None,
                    offset = 0,
                    sortBy = "operation_time:desc",
                    limit=50):
        """
        Получает список доходов за указанный период.

        :param startDate: Дата начала периода (по умолчанию None).
        :param endDate: Дата окончания периода (по умолчанию None).
        :return: Ответ от API в формате JSON.
        """
        url = f"{self.ENDPOINT}/incomes"

        # Формирование параметров запроса
        params = {
            "from": startDate.replace(microsecond=0).astimezone().isoformat() if startDate else None,
            "to": endDate.replace(microsecond=0).astimezone().isoformat() if endDate else None,
            "offset": offset,
            "sortBy": sortBy,
            "limit": limit
        }
        params = {k: v for k, v in params.items() if v is not None}

        try:
            async with self._session.get(url, headers=self.storage.get_auth_headers(), params=params, timeout=5) as response:
                json = await response.json()
                if response.status == 200:
                    return Incomes(**json)
                
                self.__logger.critical(json)
                return None

        except aiohttp.ClientError as e:
            self.__logger.critical(e)
            return None
        except asyncio.TimeoutError:
            self.__logger.critical("Timeout: API не ответил вовремя")
            return None




