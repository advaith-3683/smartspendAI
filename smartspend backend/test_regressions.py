"""Regression suite using temporary databases; never reads the project's .env."""
import os, tempfile, unittest, sqlite3, json, threading, time, socket
from contextlib import closing
from pathlib import Path
from decimal import Decimal
from datetime import date, datetime
from urllib.request import Request, build_opener, HTTPCookieProcessor
from urllib.error import HTTPError
from http.cookiejar import CookieJar
from concurrent.futures import ThreadPoolExecutor
from test_environment import TEMP
import main, models, auth, services, ingestion, schemas
from database import SessionLocal, engine, Base
from migrations import migrate

class Regressions(unittest.TestCase):
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
        cls.server.should_exit = True; cls.thread.join(5); engine.dispose(); TEMP.cleanup()
    def setUp(self): main._rate_buckets.clear()
    def client(self): return build_opener(HTTPCookieProcessor(CookieJar()))
    def call(self, client, path, data=None, method=None, headers=None):
        request = Request(self.base + path, data=json.dumps(data).encode() if data is not None else None,
                          method=method, headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            with client.open(request) as response: return response.status, json.load(response), response.headers
        except HTTPError as error:
            with error:
                return error.code, json.load(error), error.headers
    def signup(self, username):
        client = self.client()
        status, body, headers = self.call(client, '/auth/signup', {'email': username + '@example.com', 'password': 'long-test-password', 'name': ' Test ', 'monthly_income': 50000})
        self.assertEqual(status, 200, body); self.assertIn('HttpOnly', headers.get('Set-Cookie'))
        return client, body['id']
    def test_auth_ownership_logout_legacy(self):
        a, aid = self.signup('alice'); b, bid = self.signup('bob')
        self.assertEqual(self.call(self.client(), f'/transactions/{aid}')[0], 401)
        for path in (f'/users/{aid}', f'/transactions/{aid}', f'/bills/{aid}?year=2026&month=2', f'/coach/history/{aid}', f'/pace/{aid}?year=2026&month=2', f'/subscriptions/{aid}'):
            self.assertEqual(self.call(b, path)[0], 404, path)
        self.assertEqual(self.call(b, '/transactions', {'user_id': aid, 'amount': 2, 'category': 'Food', 'date': '2026-02-01'})[0], 403)
        status, bill, _ = self.call(a, '/bills', {'user_id': aid, 'name': 'Rent', 'category': 'Rent', 'amount': 100, 'due_day': 31})
        self.assertEqual(status, 200, bill)
        self.assertEqual(self.call(b, f"/bills/{bill['id']}/pay?year=2026&month=2", {}, 'POST')[0], 404)
        self.assertEqual(self.call(b, f"/bills/{bill['id']}", method='DELETE')[0], 404)
        self.assertEqual(self.call(a, '/auth/me', {'name': 'Updated', 'monthly_income': 0}, 'PATCH')[1]['name'], 'Updated')
        self.assertEqual(self.call(a, '/auth/me')[0], 200)
        self.assertEqual(self.call(a, '/auth/logout', {}, 'POST')[0], 200)
        self.assertEqual(self.call(a, '/auth/me')[0], 401)
        self.assertEqual(self.call(a, '/auth/login', {'email': 'alice@example.com', 'password': 'long-test-password'})[0], 200)
        self.assertEqual(self.call(a, '/admin/reset-database', {}, 'POST')[0], 404)
        with SessionLocal() as db:
            legacy = models.User(name='legacy', monthly_income=123); db.add(legacy); db.commit(); legacy_id = legacy.id
        self.assertEqual(self.call(a, f'/users/{legacy_id}')[0], 404)
    def test_expiry_rate_cors(self):
        client, uid = self.signup('expiry')
        self.assertEqual(self.call(client, '/auth/me', {'name': 'x', 'monthly_income': 1}, 'PATCH', {'Origin': 'https://evil.test'})[0], 403)
        with SessionLocal() as db:
            db.query(auth.AuthSession).filter_by(user_id=uid).update({'expires_at': datetime(2000, 1, 1)}); db.commit()
        self.assertEqual(self.call(client, '/auth/me')[0], 401)
        for _ in range(11): result = self.call(client, '/auth/login', {'email': 'missing@example.com', 'password': 'long-test-password'})
        self.assertEqual(result[0], 429); self.assertIn('Retry-After', result[2])
    def test_validation(self):
        for value in (-1, 0, 'NaN', 'Infinity', '1.001', 1000000001):
            with self.assertRaises(ValueError): schemas.TransactionCreate(user_id=1, amount=value, category='Food', date='2026-01-01')
        for field, value in (('month', 13), ('year', 0), ('category', ' ')):
            data = dict(user_id=1, category='Food', monthly_limit=1, month=1, year=2026); data[field] = value
            with self.assertRaises(ValueError): schemas.BudgetCreate(**data)
    def test_bill_atomic_retries_deletion_read_purity(self):
        client, uid = self.signup('bills')
        _, bill, _ = self.call(client, '/bills', {'user_id': uid, 'name': 'Broadband', 'category': 'Bills', 'amount': '10.23', 'due_day': 31})
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.call(client, f"/bills/{bill['id']}/pay?year=2026&month=2", {}, 'POST')[0], range(4)))
        self.assertEqual(results, [200] * 4)
        with SessionLocal() as db:
            txns = db.query(models.Transaction).filter_by(user_id=uid).all(); self.assertEqual(len(txns), 1)
            self.assertEqual(txns[0].amount, Decimal('10.23')); self.assertEqual(txns[0].date, date(2026, 2, 28)); tid = txns[0].id
        self.assertEqual(self.call(client, f'/transactions/item/{tid}', method='DELETE')[0], 200)
        _, bills, _ = self.call(client, f'/bills/{uid}?year=2026&month=2')
        self.assertEqual(bills[0]['status'], 'overdue'); self.assertEqual(bills[0]['due_day'], 28)
        with SessionLocal() as db: self.assertEqual(db.query(models.Budget).filter_by(user_id=uid).count(), 0)
        self.call(client, f"/bills/{bill['id']}/pay?year=2026&month=2", {}, 'POST')
        self.call(client, f"/bills/{bill['id']}", method='DELETE')
        with SessionLocal() as db: self.assertEqual(db.query(models.Transaction).filter_by(user_id=uid).count(), 1)
    def test_projections_categories_purchase_period(self):
        client, uid = self.signup('pace')
        self.call(client, '/budgets', {'user_id': uid, 'category': ' food ', 'monthly_limit': 1000, 'year': 2026, 'month': 2})
        for amount, frequency, day in ((100, 'daily', 1), (200, 'monthly', 1), (300, 'one_time', 1), (900, 'daily', 20)):
            self.call(client, '/transactions', {'user_id': uid, 'category': 'food', 'amount': amount, 'frequency': frequency, 'date': f'2026-02-{day:02}'})
        with SessionLocal() as db:
            pace = services.calculate_pace(db, uid, 'Food', 2026, 2, date(2026, 2, 10))
            self.assertEqual(pace['spent_so_far'], Decimal(600)); self.assertEqual(pace['projected_spend'], Decimal(780))
        _, result, _ = self.call(client, '/buy-decision', {'user_id': uid, 'category': ' food ', 'item_name': 'meal', 'item_cost': 1, 'year': 2026, 'month': 3})
        self.assertFalse(result['budget_exists']); self.assertIsNone(result['would_exceed_budget'])
        _, txn, _ = self.call(client, '/transactions', {'user_id': uid, 'category': 'Veterinary', 'amount': 1, 'date': '2026-02-01'})
        self.assertEqual(txn['category'], 'Veterinary')
    def test_savings_fixed_costs_missing_history(self):
        _, uid = self.signup('savings')
        with SessionLocal() as db:
            db.get(models.User, uid).monthly_income = 0
            db.add(models.Transaction(user_id=uid, amount=1000, category='Rent', date=date.today().replace(day=1) - services.timedelta(days=1), source='manual', frequency='monthly')); db.commit()
            plan = services.compute_savings_plan(db, uid, Decimal(10000), 1)
            self.assertFalse(plan['achievable']); self.assertFalse(plan['history_reliable']); self.assertEqual(plan['categories'][0]['cut_amount'], 0)
    def test_import_direction_ambiguity(self):
        result = ingestion.parse_csv_statement(b'Date,Description,Credit Amount,Debit Amount\n01/02/2026,Salary,50000,\n02/02/2026,Cafe,,12.34\n')
        self.assertEqual(len(result), 1); self.assertEqual(result[0]['amount'], Decimal('12.34'))
        self.assertEqual(len(ingestion.parse_csv_statement(b'Date,Description,Amount\n01/02/2026,Debit,-20\n02/02/2026,Credit,30\n')), 1)
        self.assertEqual(len(ingestion.parse_csv_statement(b'Date,Description,Amount,Type\n01/02/2026,Cafe,20,DR\n02/02/2026,Salary,300,CR\n')), 1)
        self.assertEqual(ingestion.parse_csv_statement(b'Date,Description,Amount\n01/02/2026,Ambiguous,20\n'), [])
    def test_digest_cross_month_arrears_and_recurring_definition(self):
        _, uid = self.signup('digest')
        with SessionLocal() as db:
            bill = models.Bill(user_id=uid, name='Utility', category='Bills', amount=100, due_day=2, created_at=datetime(2026, 1, 1))
            db.add(bill)
            db.add_all([models.Transaction(user_id=uid, amount=10, category='Food', date=date(2026, 1, 30), source='manual', frequency='daily'), models.Transaction(user_id=uid, amount=100, category='Bills', date=date(2026, 1, 30), source='bill', frequency='monthly')])
            db.commit()
            digest = services.get_weekly_digest_data(db, uid, date(2026, 1, 30))
            self.assertEqual(digest['total_this_week'], 10)
            self.assertEqual(digest['total_last_week'], 0)
            due = {b['due_date'] for b in digest['bills_due_soon']}
            self.assertIn(date(2026, 1, 2), due); self.assertIn(date(2026, 2, 2), due)
    def test_bill_unpay_retries_and_money_sum(self):
        client, uid = self.signup('unpay')
        _, bill, _ = self.call(client, '/bills', {'user_id': uid, 'name': 'Fixed', 'category': 'Bills', 'amount': '0.10', 'due_day': 1})
        self.call(client, f"/bills/{bill['id']}/pay?year=2026&month=2", {}, 'POST')
        for _ in range(2): self.assertEqual(self.call(client, f"/bills/{bill['id']}/unpay?year=2026&month=2", {}, 'POST')[0], 200)
        with SessionLocal() as db:
            self.assertEqual(db.query(models.Transaction).filter_by(user_id=uid).count(), 0)
            db.add(models.Budget(user_id=uid, category='Food', monthly_limit=1, year=2026, month=2))
            for amount in ('0.10', '0.20'): db.add(models.Transaction(user_id=uid, category='Food', amount=Decimal(amount), date=date(2026, 2, 1), source='manual', frequency='one_time'))
            db.commit()
            result = services.evaluate_purchase(db, uid, 'Food', Decimal('0.70'), 2026, 2)
            self.assertEqual(result['remaining_budget_after'], 0)
    def test_limits_and_ai_failure_preserve_deterministic_results(self):
        client, uid = self.signup('limits')
        self.assertEqual(self.call(client, f'/transactions/{uid}?year=2026&month=13')[0], 422)
        self.assertEqual(self.call(client, '/ingest/commit', {'user_id': uid, 'transactions': []})[0], 422)
        self.assertEqual(self.call(client, f'/coach/chat/{uid}', {'message': 'x' * 4001})[0], 422)
        self.assertEqual(self.call(client, f'/savings-goal/{uid}', {'target_amount': 100, 'months': 2})[0], 200)
        self.assertEqual(self.call(client, f'/coach/digest/{uid}')[0], 200)
        self.assertEqual(self.call(client, f'/coach/{uid}')[0], 503)
    def test_ai_timeout_and_output_limits_without_network(self):
        from unittest.mock import patch, MagicMock
        import llm_coach
        model = MagicMock(); model.generate_content.return_value.text = 'x' * 10000
        with patch.object(llm_coach, '_ensure_configured'), patch.object(llm_coach, 'genai', MagicMock(GenerativeModel=MagicMock(return_value=model))):
            self.assertEqual(len(llm_coach.get_coaching_advice('Test', 0, [])), 8000)
            kwargs = model.generate_content.call_args.kwargs
            self.assertEqual(kwargs['request_options']['timeout'], 30)
            self.assertEqual(kwargs['generation_config']['max_output_tokens'], 1200)
    def test_logout_revokes_copied_cookie_and_route_coverage(self):
        client, uid = self.signup('revocation')
        cookie = next(h for h in client.handlers if isinstance(h, HTTPCookieProcessor)).cookiejar
        copied = '; '.join(f'{c.name}={c.value}' for c in cookie)
        self.call(client, '/auth/logout', {}, 'POST')
        self.assertEqual(self.call(self.client(), '/auth/me', headers={'Cookie': copied})[0], 401)
        from fastapi.routing import APIRoute
        for route in main.app.routes:
            if isinstance(route, APIRoute) and not route.path.startswith('/auth/') and route.path != '/':
                self.assertIn(auth.authorize, [d.call for d in route.dependant.dependencies], route.path)
    def test_chat_failure_rolls_back_expenses(self):
        from unittest.mock import patch
        client, uid = self.signup('chatrollback')
        def fail(*args, **kwargs):
            kwargs['log_expense_fn'](amount=123, category='Food')
            raise ValueError('mock service failure')
        with patch.object(main.llm_coach, 'chat_reply', side_effect=fail):
            self.assertEqual(self.call(client, f'/coach/chat/{uid}', {'message': 'Spent 123 on food'})[0], 502)
        with SessionLocal() as db:
            self.assertEqual(db.query(models.Transaction).filter_by(user_id=uid).count(), 0)
            self.assertEqual(db.query(models.ChatMessage).filter_by(user_id=uid).count(), 0)
    def test_upload_limit(self):
        client, uid = self.signup('upload')
        boundary = 'smartspend-test-boundary'
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="large.csv"\r\nContent-Type: text/csv\r\n\r\n'.encode() + b'x' * (5 * 1024 * 1024 + 1) + f'\r\n--{boundary}--\r\n'.encode())
        request = Request(self.base + '/ingest/statement', data=body, headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
        with self.assertRaises(HTTPError) as caught: client.open(request)
        self.assertEqual(caught.exception.code, 413); caught.exception.close()
    def test_full_persistent_account_flow_and_isolation(self):
        from unittest.mock import patch
        client, uid = self.signup('persistent')
        expense = {'user_id': uid, 'amount': 12.34, 'category': 'Food', 'date': '2026-10-01', 'source': 'manual', 'frequency': 'daily'}
        status, transaction, _ = self.call(client, '/transactions', expense)
        self.assertEqual(status, 200)
        self.assertEqual(self.call(client, '/budgets', {'user_id': uid, 'category': 'Food', 'monthly_limit': 500, 'year': 2026, 'month': 10})[0], 200)
        self.assertEqual(self.call(client, '/bills', {'user_id': uid, 'name': 'Internet', 'category': 'Bills', 'amount': 50, 'due_day': 4})[0], 200)
        with patch.object(main.llm_coach, 'chat_reply', return_value='Your account history is saved.'):
            self.assertEqual(self.call(client, f'/coach/chat/{uid}', {'message': 'Help me review this month'})[0], 200)
        self.call(client, '/auth/logout', {}, 'POST')
        # A separate cookie jar models a different browser/device.
        fresh = self.client()
        self.assertEqual(self.call(fresh, '/auth/login', {'email': 'persistent@example.com', 'password': 'long-test-password'})[0], 200)
        self.assertEqual(self.call(fresh, '/auth/me')[1]['id'], uid)
        self.assertEqual(self.call(fresh, f'/transactions/{uid}?year=2026&month=10')[1][0]['amount'], 12.34)
        self.assertEqual(self.call(fresh, f'/budgets/{uid}?year=2026&month=10')[1][0]['monthly_limit'], 500)
        self.assertEqual(self.call(fresh, f'/bills/{uid}?year=2026&month=10')[1][0]['name'], 'Internet')
        self.assertEqual(len(self.call(fresh, f'/coach/history/{uid}')[1]), 2)
        self.assertEqual(self.call(fresh, '/transactions', {**expense, 'amount': 5})[0], 200)
        self.assertEqual(len(self.call(fresh, f'/transactions/{uid}')[1]), 2)
        other, oid = self.signup('persistent-other')
        self.assertEqual(self.call(other, f"/transactions/item/{transaction['id']}", {**expense, 'user_id': oid}, 'PATCH')[0], 404)
        self.assertEqual(self.call(other, f"/transactions/item/{transaction['id']}", method='DELETE')[0], 404)
        self.assertEqual(self.call(other, f'/coach/history/{uid}', method='DELETE')[0], 404)
        self.assertEqual(self.call(fresh, f'/coach/history/{uid}')[0], 200)
    def test_coco_requires_explicit_save_cancel_and_survives_login(self):
        from unittest.mock import patch
        client, uid = self.signup('proposals')
        def propose(*args, **kwargs):
            kwargs['log_expense_fn'](amount=25.50, category='Food', merchant='Cafe')
            return 'Review the proposal and press Save or Cancel.'
        with patch.object(main.llm_coach, 'chat_reply', side_effect=propose):
            status, response, _ = self.call(client, f'/coach/chat/{uid}', {'message': 'I spent 25.50 at Cafe'})
        self.assertEqual(status, 200, response)
        proposal = response['proposed_expenses'][0]
        self.assertEqual(self.call(client, f'/transactions/{uid}')[1], [])
        self.call(client, '/auth/logout', {}, 'POST')
        browser = self.client(); self.call(browser, '/auth/login', {'email': 'proposals@example.com', 'password': 'long-test-password'})
        self.assertEqual(self.call(browser, f'/coach/proposals/{uid}')[1][0]['id'], proposal['id'])
        other, _ = self.signup('proposal-other')
        self.assertEqual(self.call(other, f"/coach/proposals/{proposal['id']}/save", {}, 'POST')[0], 404)
        for _ in range(2): self.assertEqual(self.call(browser, f"/coach/proposals/{proposal['id']}/save", {}, 'POST')[0], 200)
        self.assertEqual(len(self.call(browser, f'/transactions/{uid}')[1]), 1)
        main._rate_buckets.clear()
        with patch.object(main.llm_coach, 'chat_reply', side_effect=propose):
            second = self.call(browser, f'/coach/chat/{uid}', {'message': 'Another expense'})[1]['proposed_expenses'][0]
        self.assertEqual(self.call(browser, f"/coach/proposals/{second['id']}/cancel", {}, 'POST')[0], 200)
        self.assertEqual(len(self.call(browser, f'/transactions/{uid}')[1]), 1)
    def test_restart_keeps_account_session_and_records(self):
        import subprocess, sys
        client, uid = self.signup('restart')
        self.call(client, '/transactions', {'user_id': uid, 'category': 'Travel', 'amount': 100, 'date': '2026-10-01'})
        # Start a fresh Python process against the same isolated disk database.
        sock = socket.socket(); sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]; sock.close()
        process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', str(port), '--no-proxy-headers'], cwd=Path(__file__).parent, env=os.environ.copy(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        old_base = self.base
        try:
            for _ in range(150):
                try:
                    with self.client().open(f'http://127.0.0.1:{port}/'): break
                except Exception: time.sleep(.1)
            self.base = f'http://127.0.0.1:{port}'
            self.assertEqual(self.call(client, '/auth/me')[1]['id'], uid)
            self.assertEqual(len(self.call(client, f'/transactions/{uid}')[1]), 1)
            new_browser = self.client()
            self.assertEqual(self.call(new_browser, '/auth/login', {'email': 'restart@example.com', 'password': 'long-test-password'})[0], 200)
            self.assertEqual(self.call(new_browser, '/transactions', {'user_id': uid, 'category': 'Travel', 'amount': 5, 'date': '2026-10-02'})[0], 200)
        finally:
            self.base = old_base; process.terminate(); process.wait(timeout=10)
        self.assertEqual(len(self.call(client, f'/transactions/{uid}')[1]), 2)
    def test_production_storage_guard_and_postgres_schema(self):
        from unittest.mock import patch
        from database import build_engine
        with patch.dict(os.environ, {'APP_ENV': 'production', 'PERSISTENT_DATA_DIR': ''}):
            with self.assertRaises(RuntimeError): build_engine('sqlite:///ephemeral.db')
            with self.assertRaises(RuntimeError): build_engine('postgresql+psycopg://user:password@localhost/db')
        from sqlalchemy.schema import CreateTable
        from sqlalchemy.dialects.postgresql import dialect
        ddl = str(CreateTable(models.Transaction.__table__).compile(dialect=dialect()))
        self.assertIn('BIGINT', ddl)
    def test_import_retry_is_idempotent(self):
        client, uid = self.signup('import-retry')
        batch = {'user_id': uid, 'idempotency_key': 'test-batch-key-0123456789', 'transactions': [{'amount': 10.25, 'category': 'Food', 'date': '2026-10-01', 'source': 'statement'}]}
        for _ in range(2): self.assertEqual(self.call(client, '/ingest/commit', batch)[1]['inserted'], 1)
        self.assertEqual(len(self.call(client, f'/transactions/{uid}')[1]), 1)
    def test_transaction_edit_owner_and_bill_protection(self):
        client, uid = self.signup('edit-owner')
        payload = {'user_id': uid, 'amount': 1, 'category': 'Food', 'date': '2026-10-01'}
        transaction = self.call(client, '/transactions', payload)[1]
        response = self.call(client, f"/transactions/item/{transaction['id']}", {**payload, 'amount': 2.25}, 'PATCH')
        self.assertEqual(response[0], 200); self.assertEqual(response[1]['amount'], 2.25)
        self.assertEqual(self.call(client, f'/bills/upcoming/{uid}')[0], 200)
    def test_concurrent_migrations_convert_money_once(self):
        from sqlalchemy import create_engine
        path = Path(TEMP.name) / 'concurrent-legacy.db'
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, monthly_income FLOAT NOT NULL, created_at DATETIME)')
            db.execute("INSERT INTO users VALUES (1, 'Original', 12.34, '2020-01-01')")
        def run(_):
            database = create_engine('sqlite:///' + str(path).replace('\\', '/'), connect_args={'timeout': 30})
            try: migrate(database, Base.metadata)
            finally: database.dispose()
        with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(run, range(2)))
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('SELECT monthly_income FROM users').fetchone()[0], 1234)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 5)
        self.assertEqual(len(list(path.parent.glob(path.name + '.backup-*'))), 1)
    def test_failed_migration_rolls_back_money_conversion(self):
        from sqlalchemy import create_engine
        path = Path(TEMP.name) / 'invalid-legacy.db'
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, monthly_income FLOAT NOT NULL, created_at DATETIME)')
            db.execute("INSERT INTO users VALUES (1, 'Original', 12.34, '2020-01-01')")
            db.execute('CREATE TABLE transactions (id INTEGER PRIMARY KEY, amount FLOAT NOT NULL)')
            db.execute('INSERT INTO transactions VALUES (1, ?)', (float('inf'),))
        database = create_engine('sqlite:///' + str(path).replace('\\', '/'))
        try:
            with self.assertRaises(RuntimeError): migrate(database, Base.metadata)
        finally: database.dispose()
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('SELECT monthly_income FROM users').fetchone()[0], 12.34)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 0)
        self.assertEqual(len(list(path.parent.glob(path.name + '.backup-*'))), 1)
    def test_table_pdf_import_chooses_debits(self):
        # A generated, isolated table PDF exercises actual pdfplumber extraction.
        lines = ['0.5 w']
        for x in (40, 145, 300, 410, 520): lines.append(f'{x} 665 m {x} 740 l S')
        for y in (740, 715, 690, 665): lines.append(f'40 {y} m 520 {y} l S')
        rows = [('Date', 'Description', 'Credit Amount', 'Debit Amount'), ('01/02/2026', 'Salary', '50000', ''), ('02/02/2026', 'Cafe', '', '12.34')]
        for row, y in zip(rows, (724, 699, 674)):
            for text_value, x in zip(row, (44, 149, 304, 414)):
                lines.append(f'BT /F1 9 Tf {x} {y} Td ({text_value}) Tj ET')
        stream = '\n'.join(lines).encode()
        objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>', b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>', f'<< /Length {len(stream)} >>\nstream\n'.encode() + stream + b'\nendstream', b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
        pdf = bytearray(b'%PDF-1.4\n'); offsets = [0]
        for i, obj in enumerate(objects, 1):
            offsets.append(len(pdf)); pdf.extend(f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n')
        xref = len(pdf); pdf.extend(f'xref\n0 {len(objects) + 1}\n0000000000 65535 f \n'.encode())
        for offset in offsets[1:]: pdf.extend(f'{offset:010} 00000 n \n'.encode())
        pdf.extend(f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode())
        result = ingestion.parse_pdf_statement(bytes(pdf))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['merchant'], 'Cafe')
        self.assertEqual(result[0]['amount'], Decimal('12.34'))
        self.assertEqual(result[0]['date'], '2026-02-02')
    def test_legacy_migration_backup_idempotence(self):
        from sqlalchemy import create_engine
        path = Path(TEMP.name) / 'legacy.db'
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, monthly_income FLOAT NOT NULL, created_at DATETIME)')
            db.execute("INSERT INTO users VALUES (1, 'Original', 1234.565, '2020-01-01')")
        legacy_engine = create_engine('sqlite:///' + str(path).replace('\\', '/'))
        migrate(legacy_engine, Base.metadata); migrate(legacy_engine, Base.metadata)
        with closing(sqlite3.connect(path)) as db, db: self.assertEqual(db.execute('SELECT monthly_income FROM users').fetchone()[0], 123457)
        backups = list(path.parent.glob('legacy.db.backup-*')); self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as db: self.assertEqual(db.execute('SELECT monthly_income FROM users').fetchone()[0], 1234.565)
        legacy_engine.dispose()
if __name__ == '__main__': unittest.main()
