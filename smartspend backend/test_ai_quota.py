"""Quota tests use disposable databases and mocked Gemini; never real keys/calls."""
import unittest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch
import test_environment
import auth, models, llm_coach
from database import Base
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from ai_quota import reserve_gemini_call, GeminiDailyLimitReached


class GeminiQuotaTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='gemini-quota-')
        self.url = 'sqlite:///' + (Path(self.directory.name) / 'quota.db').as_posix()
        self.engine = create_engine(self.url, connect_args={'timeout': 30, 'check_same_thread': False})
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine)
        with self.factory() as db:
            first = models.User(name='First', monthly_income=1000)
            second = models.User(name='Second', monthly_income=1000)
            db.add_all([first, second]); db.commit()
            self.uid, self.other = first.id, second.id
        self.instant = datetime(2026, 10, 31, 23, 30, tzinfo=timezone.utc)

    def tearDown(self):
        self.engine.dispose()
        self.directory.cleanup()

    def reserve(self, user_id=None, now=None):
        return reserve_gemini_call(user_id or self.uid, session_factory=self.factory, now=now or self.instant)

    def count(self):
        with self.factory() as db:
            return db.scalar(select(func.count()).select_from(models.GeminiCall).where(models.GeminiCall.user_id == self.uid))

    def test_four_calls_per_account_survive_engine_restart(self):
        for _ in range(4): self.reserve()
        with self.assertRaises(GeminiDailyLimitReached): self.reserve()
        self.reserve(self.other)
        self.assertEqual(self.count(), 4)
        self.engine.dispose()
        self.engine = create_engine(self.url)
        self.factory = sessionmaker(bind=self.engine)
        with self.assertRaises(GeminiDailyLimitReached): self.reserve()

    def test_rolling_window_does_not_reset_at_midnight_and_expires_exactly(self):
        for minutes in (0, 10, 20, 30): self.reserve(now=self.instant + timedelta(minutes=minutes))
        for delta in (timedelta(hours=1), timedelta(hours=24) - timedelta(microseconds=1)):
            with self.assertRaises(GeminiDailyLimitReached): self.reserve(now=self.instant + delta)
        self.reserve(now=self.instant + timedelta(hours=24))
        with self.assertRaises(GeminiDailyLimitReached) as caught:
            self.reserve(now=self.instant + timedelta(hours=24))
        self.assertEqual(caught.exception.retry_at, (self.instant + timedelta(hours=24, minutes=10)).replace(tzinfo=None))

    def test_concurrent_requests_cannot_exceed_four(self):
        def attempt(_):
            try: self.reserve(); return True
            except GeminiDailyLimitReached: return False
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(attempt, range(12)))
        self.assertEqual(sum(results), 4)
        self.assertEqual(self.count(), 4)

    def test_failed_provider_and_fallback_requests_both_count(self):
        requests = []
        class Model:
            def __init__(self, name, **kwargs): self.name = name
            def generate_content(self, *args, **kwargs):
                requests.append(self.name)
                if self.name == 'primary': raise TimeoutError('Provider unavailable')
                return SimpleNamespace(text='Advice')
        with patch.object(llm_coach, '_ensure_configured'), patch.multiple(llm_coach,
                genai=SimpleNamespace(GenerativeModel=Model), MODEL_NAME='primary',
                FALLBACK_MODEL='secondary', _unavailable_until={}):
            for _ in range(3):
                self.assertEqual(llm_coach.get_coaching_advice('First', 1000, [], reserve_call=self.reserve), 'Advice')
            with self.assertRaises(GeminiDailyLimitReached):
                llm_coach.get_coaching_advice('First', 1000, [], reserve_call=self.reserve)
            self.assertNotIn('secondary', llm_coach._unavailable_until, 'Account quota must not cool down a healthy provider')
        self.assertEqual(requests, ['primary', 'secondary', 'secondary', 'secondary'])
        self.assertEqual(self.count(), 4)

    def test_every_automatic_tool_round_trip_is_metered(self):
        requests = []
        class Model:
            def __init__(self, name, **kwargs): pass
            def generate_content(self, *args, **kwargs):
                requests.append('provider request')
                return SimpleNamespace(text='Reply')
            def start_chat(self, **kwargs):
                def send(*args, **options):
                    for _ in range(5): response = self.generate_content('history', **options)
                    return response
                return SimpleNamespace(send_message=send)
        with patch.object(llm_coach, '_ensure_configured'), patch.multiple(llm_coach,
                genai=SimpleNamespace(GenerativeModel=Model), _unavailable_until={}):
            with self.assertRaises(GeminiDailyLimitReached):
                llm_coach.chat_reply('First', 1000, [], 0, 1000, [], [], 'Hello', reserve_call=self.reserve)
        self.assertEqual(len(requests), 4)
        self.assertEqual(self.count(), 4)

    def test_invalid_account_and_missing_guard_fail_closed(self):
        with self.assertRaises(RuntimeError): self.reserve(user_id=999999)
        with patch.object(llm_coach, 'genai') as sdk:
            with self.assertRaises(RuntimeError): llm_coach._metered_model('primary', None)
            sdk.GenerativeModel.assert_not_called()

    def test_missing_ai_configuration_does_not_consume_quota(self):
        with patch.object(llm_coach, 'GEMINI_API_KEY', ''):
            with self.assertRaises(RuntimeError):
                llm_coach.get_coaching_advice('First', 1000, [], reserve_call=self.reserve)
        self.assertEqual(self.count(), 0)

    def test_v5_upgrade_adds_quota_table_without_resetting_records(self):
        from migrations import migrate
        with self.engine.begin() as connection:
            connection.exec_driver_sql('DROP TABLE gemini_calls')
            connection.exec_driver_sql('PRAGMA user_version = 5')
        migrate(self.engine, Base.metadata)
        with self.factory() as db:
            self.assertEqual(db.get(models.User, self.uid).name, 'First')
            self.assertEqual(db.execute(__import__('sqlalchemy').text('PRAGMA user_version')).scalar(), 6)
        self.reserve()
        migrate(self.engine, Base.metadata)
        self.assertEqual(self.count(), 1)
        self.assertEqual(len(list(Path(self.directory.name).glob('*.backup-*'))), 1)


if __name__ == '__main__':
    unittest.main()
