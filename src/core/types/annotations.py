from bson import Decimal128
from pydantic_core import core_schema


from decimal import Decimal, InvalidOperation
from typing import Any


class DecimalAnnotation:

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: Any
    ) -> core_schema.CoreSchema:
        """Схема для валидации и сериализации Decimal полей."""

        def validate_to_decimal(value: Any) -> Decimal:
            """Конвертируем различные типы в Decimal."""
            if isinstance(value, Decimal):
                return value
            elif isinstance(value, Decimal128):
                return value.to_decimal()
            elif isinstance(value, str):
                try:
                    return Decimal(value)
                except InvalidOperation as e:
                    raise ValueError(f"Invalid decimal string: {value}") from e
            elif isinstance(value, (int, float)):
                # Для float есть потеря точности, но это ожидаемо
                return Decimal(str(value))
            else:
                raise ValueError(f"Cannot convert {type(value).__name__} to Decimal")

        # Схема для валидации входящих данных в Decimal
        decimal_schema = core_schema.no_info_plain_validator_function(validate_to_decimal)

        # Сериализатор для конвертации Decimal -> Decimal128 при дампе в словарь
        def serialize_to_decimal128(value: Decimal, _info) -> Decimal128:
            """Сериализуем Decimal в Decimal128 для Python dict."""
            return Decimal128(str(value))

        # Схема для конвертации Decimal -> строка при дампе в JSON
        def serialize_to_string(value: Decimal, _info) -> str:
            """Сериализуем Decimal в строку для JSON."""
            return str(value)

        return core_schema.json_or_python_schema(
            json_schema=core_schema.str_schema(),
            python_schema=core_schema.union_schema(
                [
                    core_schema.is_instance_schema(Decimal),
                    core_schema.is_instance_schema(Decimal128),
                    decimal_schema,
                ]
            ),
            # Двойная сериализация: для JSON и для Python dict
            serialization=core_schema.plain_serializer_function_ser_schema(
                function=lambda value, info=None: (
                    serialize_to_string(value, info) if info and info.mode == 'json'
                    else serialize_to_decimal128(value, info)
                ),
                return_schema=core_schema.union_schema([
                    core_schema.str_schema(),
                    core_schema.is_instance_schema(Decimal128),
                ]),
                when_used='always',
            ),
        )
        
__all__ = ['DecimalAnnotation']