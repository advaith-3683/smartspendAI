"""Durable rolling 24-hour quota, serialized per authenticated account."""
from datetime import datetime, timedelta, timezone

DAILY_LIMIT = 4
WINDOW = timedelta(hours=24)


class GeminiDailyLimitReached(RuntimeError):
    def __init__(self, retry_at):
        self.retry_at = retry_at
        super().__init__('Four Gemini calls per account per rolling 24 hours')


def reserve_gemini_call(user_id, *, session_factory=None, now=None):
    # Import lazily so optional AI imports never connect or initialize storage.
    from database import SessionLocal
    from models import User, GeminiCall
    from sqlalchemy import select, text

    factory = session_factory or SessionLocal
    # A separate committed transaction survives failed chat/tool rollbacks.
    with factory() as db:
        if db.bind.dialect.name == 'sqlite':
            db.execute(text('BEGIN IMMEDIATE'))
        else:
            # The count must see the previous lock holder's committed reservation.
            db.execute(text('SET TRANSACTION ISOLATION LEVEL READ COMMITTED'))
            db.execute(text("SET LOCAL lock_timeout = '5s'"))
            db.execute(text("SET LOCAL statement_timeout = '10s'"))
        owner = db.execute(select(User.id).where(User.id == user_id).with_for_update()).scalar_one_or_none()
        if owner is None:
            raise RuntimeError('An authenticated account is required for Gemini')
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is not None:
            instant = instant.astimezone(timezone.utc).replace(tzinfo=None)
        cutoff = instant - WINDOW
        db.query(GeminiCall).filter(GeminiCall.user_id == user_id, GeminiCall.called_at <= cutoff).delete()
        calls = db.execute(select(GeminiCall.called_at).where(
            GeminiCall.user_id == user_id, GeminiCall.called_at > cutoff
        ).order_by(GeminiCall.called_at)).scalars().all()
        if len(calls) >= DAILY_LIMIT:
            raise GeminiDailyLimitReached(calls[0] + WINDOW)
        db.add(GeminiCall(user_id=user_id, called_at=instant))
        db.commit()


def quota_for_user(user_id):
    return lambda: reserve_gemini_call(user_id)
