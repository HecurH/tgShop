from bson import Decimal128
from pydantic_core import core_schema


from decimal import Decimal, InvalidOperation
from typing import Annotated, Any


class DecimalAnnotation:
    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: Any
    ) -> core_schema.CoreSchema:
        
        def validate_to_decimal(value: Any) -> Decimal:
            """Всегда возвращаем чистый Decimal внутри модели."""
            if isinstance(value, Decimal):
                return value
            if isinstance(value, Decimal128):
                return value.to_decimal()          # ← вот ключевой момент
            if isinstance(value, str):
                try:
                    return Decimal(value)
                except InvalidOperation as e:
                    raise ValueError(f"Invalid decimal string: {value}") from e
            if isinstance(value, (int, float)):
                return Decimal(str(value))
            raise ValueError(f"Cannot convert {type(value).__name__} to Decimal")

        # Основная схема валидации (всегда прогоняем через конвертер)
        decimal_validator = core_schema.no_info_plain_validator_function(validate_to_decimal)

        def serializer(value: Decimal, info) -> str | Decimal128:
            """Сериализация: в JSON — строка, в Python/Mongo — Decimal128"""
            if info and info.mode == 'json':
                return str(value)
            return Decimal128(str(value))   # для model_dump() и сохранения в Mongo

        return core_schema.json_or_python_schema(
            json_schema=decimal_validator,
            python_schema=core_schema.union_schema([
                core_schema.is_instance_schema(Decimal),   # уже Decimal — пропускаем
                decimal_validator,                         # всё остальное (включая Decimal128) конвертируем
            ]),
            serialization=core_schema.plain_serializer_function_ser_schema(
                function=serializer,
                info_arg=True,
                return_schema=core_schema.union_schema([
                    core_schema.str_schema(),
                    core_schema.is_instance_schema(Decimal128),
                ]),
                when_used='always'
            )
        )


PydanticDecimal = Annotated[Decimal, DecimalAnnotation]
        
__all__ = ['DecimalAnnotation', 'PydanticDecimal']