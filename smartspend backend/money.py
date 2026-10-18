"""Integer minor units on disk, Decimal rupees in Python, HALF_UP at boundaries."""
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy.types import TypeDecorator, BigInteger

class Money(TypeDecorator):
    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def process_result_value(self, value, dialect):
        return Decimal(str(value)) / 100 if value is not None else None
