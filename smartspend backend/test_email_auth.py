"""Real HTTP and migration tests using the shared disposable SQLite fixture only."""
import unittest
import uuid
import socket
import threading
import time
import sqlite3
import tempfile
from pathlib import Path
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from test_environment import TEMP
import main, auth, models
from database import Base, SessionLocal
from migrations import migrate
import test_regressions as support
from sqlalchemy import create_engine, MetaData, text
from sqlalchemy.exc import IntegrityError


class EmailAuthTests(unittest.TestCase):
    client = support.Regressions.client
    call = support.Regressions.call
    setUp = support.Regressions.setUp

    @classmethod
    def setUpClass(cls):
        import uvicorn
        cls.sock = socket.socket(); cls.sock.bind(('127.0.0.1', 0))
        cls.base = f'http://127.0.0.1:{cls.sock.getsockname()[1]}'
        cls.server = uvicorn.Server(uvicorn.Config(main.app, log_level='error'))
        cls.thread = threading.Thread(target=cls.server.run, kwargs={'sockets': [cls.sock]}, daemon=True)
        cls.thread.start()
        for _ in range(100):
            if cls.server.started: break
            time.sleep(.05)
        assert cls.server.started

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True; cls.thread.join(5)
        main.engine.dispose()

    def register(self, email=None):
        email = email or uuid.uuid4().hex + '@example.com'
        client = self.client()
        result = self.call(client, '/auth/signup', {'email': email, 'name': 'Shared Display Name', 'password': 'email-test-password'})
        self.assertEqual(result[0], 200, result[1])
        return client, result[1]

    def test_normalization_validation_and_generic_login(self):
        self.assertEqual(auth.normalize_email(' A.B+Tag@EXAMPLE.COM '), 'a.b+tag@example.com')
        for invalid in ['no-at', 'x@localhost', 'a..b@example.com', 'Name <a@example.com>', 'a@', 'a b@example.com']:
            with self.assertRaises(ValueError): auth.normalize_email(invalid)
        self.assertNotEqual(auth.normalize_email('a.b@example.com'), auth.normalize_email('ab@example.com'))
        self.assertNotEqual(auth.normalize_email('ab+tag@example.com'), auth.normalize_email('ab@example.com'))
        email = uuid.uuid4().hex + '@example.com'
        client, user = self.register(' ' + email.upper() + ' ')
        self.assertEqual(user['email'], email); self.assertFalse(user['email_verified'])
        self.assertEqual(user['monthly_income'], 0)
        duplicate = self.call(self.client(), '/auth/signup', {'email': email, 'password': 'email-test-password', 'name': 'Different'})
        self.assertEqual(duplicate[0], 409)
        self.assertEqual(self.call(client, '/auth/me')[1]['id'], user['id'])
        self.call(client, '/auth/logout', {}, 'POST')
        self.assertEqual(self.call(client, '/auth/login', {'email': email.upper(), 'password': 'email-test-password'})[0], 200)
        bad = self.call(client, '/auth/login', {'email': email, 'password': 'wrong-password-long'})
        missing = self.call(client, '/auth/login', {'email': 'absent-' + email, 'password': 'wrong-password-long'})
        self.assertEqual((bad[0], bad[1]), (missing[0], missing[1])); self.assertEqual(bad[0], 401)
        self.assertEqual(self.call(client, '/auth/signup', {'email': 'bad', 'name': 'Name', 'password': 'email-test-password'})[0], 422)

    def test_concurrent_email_unique_and_names_not_unique(self):
        email = uuid.uuid4().hex + '@example.com'
        barrier = threading.Barrier(2)
        def attempt(value):
            barrier.wait()
            return self.call(self.client(), '/auth/signup', {'email': value, 'name': 'Concurrent Name', 'password': 'email-test-password'})[0]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, [email, email.upper()]))
        self.assertEqual(sorted(results), [200, 409])
        _, second = self.register()
        _, third = self.register()
        self.assertNotEqual(second['id'], third['id']); self.assertEqual(second['name'], third['name'])
        with SessionLocal() as db:
            self.assertEqual(db.query(auth.EmailAccount).filter_by(email=email).count(), 1)
            with self.assertRaises(IntegrityError):
                db.execute(text('UPDATE email_accounts SET email=:email WHERE user_id=:uid'), {'email': email.upper(), 'uid': second['id']})
                db.commit()
            db.rollback()

    def test_legacy_enrollment_preserves_records_and_isolation(self):
        account_id = 'legacy_' + uuid.uuid4().hex
        with SessionLocal() as db:
            user = models.User(name='Shared Display Name', monthly_income=123.45)
            db.add(user); db.flush(); uid = user.id
            db.add(auth.Credential(user_id=uid, username=account_id, password_hash=auth.password_hash('legacy-test-password')))
            db.add(models.ChatMessage(user_id=uid, role='user', content='Synthetic saved history'))
            db.commit()
        owner = self.client(); other, other_user = self.register()
        login = self.call(owner, '/auth/legacy-login', {'username': account_id, 'password': 'legacy-test-password'})
        self.assertEqual(login[0], 200); self.assertIsNone(login[1]['email'])
        _, transaction, _ = self.call(owner, '/transactions', {'user_id': uid, 'amount': 12.34, 'date': '2026-10-01', 'category': 'Food'})
        self.call(owner, '/budgets', {'user_id': uid, 'category': 'Food', 'monthly_limit': 100, 'year': 2026, 'month': 10})
        self.call(owner, '/bills', {'user_id': uid, 'name': 'Test bill', 'category': 'Bills', 'amount': 5, 'due_day': 1})
        endpoint = '/auth/enroll-email'
        self.assertEqual(self.call(self.client(), endpoint, {'email': 'test@example.com', 'current_password': 'legacy-test-password'})[0], 401)
        self.assertEqual(self.call(owner, endpoint, {'email': 'test@example.com', 'current_password': 'wrong-password-long'})[0], 403)
        self.assertEqual(self.call(owner, endpoint, {'email': other_user['email'], 'current_password': 'legacy-test-password'})[0], 409)
        self.assertEqual(self.call(owner, endpoint, {'email': 'test@example.com', 'current_password': 'legacy-test-password', 'user_id': other_user['id']})[0], 422)
        email = uuid.uuid4().hex + '+tag@example.com'
        result = self.call(owner, endpoint, {'email': email.upper(), 'current_password': 'legacy-test-password'})
        self.assertEqual(result[0], 200); self.assertEqual(result[1]['id'], uid); self.assertEqual(result[1]['email'], email)
        self.assertFalse(result[1]['email_verified'])
        self.assertEqual(self.call(owner, '/auth/me')[1]['id'], uid)
        for path in [f'/transactions/{uid}?year=2026&month=10', f'/budgets/{uid}?year=2026&month=10', f'/bills/{uid}?year=2026&month=10', f'/coach/history/{uid}']:
            self.assertEqual(len(self.call(owner, path)[1]), 1)
            self.assertEqual(self.call(other, path)[0], 404)
        self.assertEqual(self.call(other, f"/transactions/item/{transaction['id']}", method='DELETE')[0], 404)
        # Enrollment neither merges nor claims other users; legacy sign-in is retired for this account.
        main._rate_buckets.clear()
        self.assertEqual(self.call(self.client(), '/auth/login', {'username': account_id, 'password': 'legacy-test-password'})[0], 401)
        self.assertEqual(self.call(self.client(), '/auth/legacy-login', {'username': account_id, 'password': 'legacy-test-password'})[0], 401)
        fresh = self.client()
        self.assertEqual(self.call(fresh, '/auth/login', {'email': email, 'password': 'legacy-test-password'})[1]['id'], uid)
        self.assertEqual(self.call(fresh, endpoint, {'email': 'another@example.com', 'current_password': 'legacy-test-password'})[0], 409)

    def test_version_four_sqlite_migration_is_additive_repeatable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'legacy.db'
            engine = create_engine('sqlite:///' + path.as_posix())
            old = MetaData()
            for table in Base.metadata.sorted_tables:
                if table.name != 'email_accounts': table.to_metadata(old)
            old.create_all(engine)
            with engine.begin() as connection:
                connection.execute(text("INSERT INTO users (id,name,monthly_income) VALUES (77,'same name',12345)"))
                connection.execute(text("INSERT INTO credentials VALUES (77,'arbitrary.old.id','synthetic-hash')"))
                connection.execute(text("INSERT INTO auth_sessions VALUES ('synthetic-token',77,'2099-01-01')"))
                connection.execute(text("INSERT INTO transactions (id,user_id,amount,category,date,source,frequency) VALUES (5,77,1234,'Food','2026-10-01','manual','daily')"))
                connection.exec_driver_sql('PRAGMA user_version = 4')
                before = {t.name: connection.execute(t.select()).fetchall() for t in old.sorted_tables}
            migrate(engine, Base.metadata); migrate(engine, Base.metadata)
            with engine.connect() as connection:
                self.assertEqual(connection.exec_driver_sql('PRAGMA user_version').scalar(), 5)
                for table in old.sorted_tables: self.assertEqual(before[table.name], connection.execute(table.select()).fetchall())
                self.assertEqual(connection.execute(text('SELECT count(*) FROM email_accounts')).scalar(), 0)
            backups = list(path.parent.glob('*.backup-*'))
            self.assertEqual(len(backups), 1)
            saved = sqlite3.connect(backups[0])
            try: self.assertEqual(saved.execute('PRAGMA user_version').fetchone()[0], 4)
            finally: saved.close()
            engine.dispose()
