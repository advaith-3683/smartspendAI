"""Bounded real-process port/health tests; only disposable SQLite databases."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import urlopen, Request
from unittest.mock import MagicMock, patch
import test_environment


class StartupTests(unittest.TestCase):
    def run_server(self, fail_database=False):
        with tempfile.TemporaryDirectory(prefix='smartspend-boot-') as directory:
            path = Path(directory)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
            env = {**os.environ, 'DATABASE_URL': 'sqlite:///' + (path / 'test.db').as_posix(),
                   'GEMINI_API_KEY': 'synthetic-never-sent', 'APP_ENV': 'development',
                   'COOKIE_SECURE': 'false', 'COOKIE_SAMESITE': 'lax',
                   'CORS_ORIGINS': 'http://localhost:5173', 'PYTHONUTF8': '1'}
            code = '''
import faulthandler, sys, importlib.abc
faulthandler.dump_traceback_later(5, repeat=True)
class BlockHeavyImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'pandas' or fullname.startswith('google.generativeai'):
            raise RuntimeError('Optional dependency must not load at startup')
sys.meta_path.insert(0, BlockHeavyImports())
import main, uvicorn
'''
            if fail_database:
                code += "def fail(*args): raise RuntimeError('synthetic-private-value')\nmain.migrate = fail\n"
            code += f'''
runner = uvicorn.Server(uvicorn.Config(main.app, host='127.0.0.1', port={port}, access_log=False))
@main.app.post('/__test_shutdown')
def shutdown():
    runner.should_exit = True
    return {{'stopping': True}}
runner.run()
faulthandler.cancel_dump_traceback_later()
main.engine.dispose()
'''
            with (path / 'startup.log').open('w', encoding='utf-8') as output:
                process = subprocess.Popen([sys.executable, '-X', 'importtime', '-c', code],
                                           cwd=Path(__file__).parent, env=env, stdout=output, stderr=output)
                started = time.monotonic(); healthy = False
                try:
                    while time.monotonic() - started < 25 and process.poll() is None:
                        try:
                            with urlopen(f'http://127.0.0.1:{port}/', timeout=.5) as response:
                                self.assertEqual(response.status, 200)
                                self.assertEqual(json.load(response), {'status': 'SmartSpend AI backend running'})
                                healthy = True
                                break
                        except OSError:
                            time.sleep(.1)
                    elapsed = time.monotonic() - started
                    if healthy:
                        with urlopen(Request(f'http://127.0.0.1:{port}/__test_shutdown', data=b'', method='POST'), timeout=2):
                            pass
                    process.wait(timeout=10)
                finally:
                    if process.poll() is None:
                        process.kill(); process.wait(timeout=5)
            log = (path / 'startup.log').read_text(encoding='utf-8')
            self.assertNotIn('synthetic-private-value', log)
            self.assertNotIn('synthetic-never-sent', log)
            if fail_database:
                self.assertFalse(healthy)
                self.assertIn('"status": "failed"', log)
                self.assertNotIn('Application startup complete', log)
            else:
                self.assertTrue(healthy, 'Server failed bounded port/health verification; inspect isolated startup log')
                self.assertIn('Started server process', log)
                self.assertIn('Application startup complete', log)
                self.assertIn('"stage": "database_security", "status": "complete"', log)
                print(f'Isolated startup health HTTP 200 after {elapsed:.2f}s; optional SDK/pandas imports blocked')

    def test_real_server_binds_and_serves_health_without_optional_imports(self):
        self.run_server()

    def test_failed_required_database_check_prevents_serving_and_is_sanitized(self):
        self.run_server(fail_database=True)

    def test_lazy_ai_initialization_has_single_worker_and_bounded_wait(self):
        import llm_coach
        event = MagicMock(); event.wait.return_value = False
        with patch.multiple(llm_coach, GEMINI_API_KEY='synthetic', _configured=False,
                            _initialization_started=False, _initialization_done=event), patch.object(llm_coach.threading, 'Thread') as thread:
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError, 'initialization is unavailable'):
                    llm_coach._ensure_configured()
            self.assertEqual(thread.call_count, 1)
            self.assertTrue(thread.call_args.kwargs['daemon'])
            event.wait.assert_called_with(5)

    def test_expired_security_audit_deadline_refuses_before_any_query(self):
        from postgres_storage import audit_connection
        from sqlalchemy import MetaData
        connection = MagicMock()
        with self.assertRaises(TimeoutError):
            audit_connection(connection, MetaData(), deadline=0)
        connection.execute.assert_not_called()

    def test_optional_ai_import_failure_is_sanitized_and_completes(self):
        import llm_coach
        import threading
        event = threading.Event()
        with patch.multiple(llm_coach, _configured=False, _initialization_done=event), patch.object(llm_coach.importlib, 'import_module', side_effect=RuntimeError('synthetic-private-value')):
            llm_coach._initialize_sdk()
            self.assertTrue(event.is_set())
            self.assertFalse(llm_coach._configured)

    def test_postgres_startup_verify_keeps_audit_and_sets_query_bounds(self):
        from postgres_storage import verify_postgres
        from sqlalchemy import MetaData
        engine = MagicMock(); connection = engine.connect.return_value
        with patch('postgres_storage.audit_connection', return_value={'version': 5}) as audit:
            self.assertEqual(verify_postgres(engine, MetaData()), {'version': 5})
            self.assertIn('deadline', audit.call_args.kwargs)
            self.assertIn("statement_timeout = '15s'", str(connection.execute.call_args_list[0].args[0]))
            self.assertIn("lock_timeout = '5s'", str(connection.execute.call_args_list[1].args[0]))
        connection.close.assert_called_once()
