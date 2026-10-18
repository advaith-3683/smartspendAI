"""Sanitized CLI diagnostics. Injected failures only; no network or data writes."""
import contextlib
import io
import json
import socket
import ssl
import unittest
from unittest.mock import MagicMock, patch
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy import MetaData
from database_diagnostics import (
    DatabasePolicyError, DatabaseStageError, database_stage, diagnostic, diagnostic_json,
)

SECRET = 'do-not-log-password-or-financial-row'
URI = 'postgresql+psycopg://private-user:' + SECRET + '@private-host/private-db'


class DriverError(Exception):
    def __init__(self, state=None, message=URI):
        super().__init__(message)
        self.sqlstate = state


class DiagnosticsTests(unittest.TestCase):
    def assert_sanitized(self, output):
        for forbidden in (SECRET, URI, 'private-user', 'private-host', 'private-db', 'SELECT secret_data'):
            self.assertNotIn(forbidden, output)

    def test_sqlstate_categories_and_wrapped_driver(self):
        for state, category in [('28P01', 'authentication'), ('28000', 'authentication'),
                                ('42501', 'insufficient_privileges'), ('42601', 'sql_or_schema'),
                                ('42P01', 'sql_or_schema'), ('3F000', 'sql_or_schema'),
                                ('08006', 'network_or_availability'), ('53300', 'connection_capacity'),
                                ('57014', 'query_or_lock_timeout'), ('23505', 'constraint')]:
            with self.subTest(state=state):
                original = DriverError(state)
                wrapped = OperationalError('SELECT secret_data', {'password': SECRET}, original)
                result = diagnostic(DatabaseStageError('migration', wrapped))
                self.assertEqual(result['stage'], 'migration')
                self.assertEqual(result['sqlstate'], state)
                self.assertEqual(result['exception_class'], 'OperationalError')
                self.assertEqual(result['driver_exception_class'], 'DriverError')
                self.assertEqual(result['category'], category)
                self.assert_sanitized(json.dumps(result))

    def test_connection_failures_without_sqlstate(self):
        cases = [(socket.gaierror(URI), 'dns'), (TimeoutError(URI), 'timeout'),
                 (ssl.SSLError(URI), 'tls'), (ConnectionRefusedError(URI), 'network_or_availability'),
                 (DriverError(message='password authentication failed ' + URI), 'authentication'),
                 (DriverError(message='could not translate host name ' + URI), 'dns'),
                 (DriverError(message='certificate verify failed ' + URI), 'tls'),
                 (DriverError(message='timeout expired ' + URI), 'timeout')]
        for error, category in cases:
            result = diagnostic(DatabaseStageError('connection', error))
            self.assertEqual(result['category'], category)
            self.assertIsNone(result['sqlstate'])
            self.assert_sanitized(json.dumps(result))

    def test_authoritative_state_beats_sensitive_message_hints(self):
        result = diagnostic(DriverError('42501', 'password authentication failed ' + URI))
        self.assertEqual(result['category'], 'insufficient_privileges')

    def test_unknown_runtime_error_never_prints_its_message(self):
        self.assert_sanitized(diagnostic_json(RuntimeError(URI)))
        self.assertEqual(diagnostic(RuntimeError(URI))['category'], 'unclassified')
        result = diagnostic(DriverError('BAD-' + SECRET))
        self.assertIsNone(result['sqlstate'])
        self.assert_sanitized(json.dumps(result))

    def test_safe_policy_failure_and_nested_stage_preserved(self):
        with self.assertRaises(DatabaseStageError) as caught:
            with database_stage('migration'):
                with database_stage('security_verification'):
                    raise DatabasePolicyError('rls_disabled')
        result = diagnostic(caught.exception)
        self.assertEqual(result['stage'], 'security_verification')
        self.assertEqual(result['policy_code'], 'rls_disabled')
        self.assertEqual(result['category'], 'security_audit')
        self.assert_sanitized(str(caught.exception))

    def test_legacy_pgcode_and_cyclic_exception_chain(self):
        error = DriverError()
        error.pgcode = '28P01'
        error.orig = error
        self.assertEqual(diagnostic(error)['sqlstate'], '28P01')

    def test_cli_bootstrap_failure_is_safe_and_nonzero(self):
        import manage_database
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(manage_database, 'load_backend', side_effect=RuntimeError(URI)), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = manage_database.main(['migrate'])
        self.assertEqual(status, 1)
        self.assertEqual(stdout.getvalue(), '')
        self.assertEqual(json.loads(stderr.getvalue())['stage'], 'connection')
        self.assert_sanitized(stderr.getvalue())

    def test_cli_preserves_audit_failure_in_migrate(self):
        import manage_database
        engine = MagicMock()
        output = io.StringIO()
        failure = DatabaseStageError('security_verification', ProgrammingError('SELECT secret_data', {'private': SECRET}, DriverError('42883')))
        with patch.object(manage_database, 'load_backend', return_value=(engine, MetaData())), patch.object(manage_database, 'execute_operation', side_effect=failure), contextlib.redirect_stderr(output):
            self.assertEqual(manage_database.main(['migrate']), 1)
        result = json.loads(output.getvalue())
        self.assertEqual(result['stage'], 'security_verification')
        self.assertEqual(result['sqlstate'], '42883')
        self.assert_sanitized(output.getvalue())
        engine.dispose.assert_called_once()

    def test_actual_migration_and_verify_connection_failures(self):
        from postgres_storage import migrate_postgres, verify_postgres
        for operation in (migrate_postgres, verify_postgres):
            engine = MagicMock(); engine.connect.side_effect = DriverError('28P01')
            with self.assertRaises(DatabaseStageError) as caught:
                operation(engine, MetaData())
            self.assertEqual(diagnostic(caught.exception)['stage'], 'connection')

    def test_migration_sql_and_audit_stages_keep_rollback(self):
        from postgres_storage import migrate_postgres
        engine, connection = MagicMock(), MagicMock()
        engine.connect.return_value = connection
        connection.execute.side_effect = DriverError('42501')
        with self.assertRaises(DatabaseStageError) as caught:
            migrate_postgres(engine, MetaData())
        self.assertEqual(diagnostic(caught.exception)['stage'], 'migration')
        # Transaction manager receives the exception, not a swallowed failure.
        self.assertIsNotNone(connection.begin.return_value.__exit__.call_args.args[0])
        connection.close.assert_called_once()

    def test_migration_audit_failure_is_not_mislabeled_and_rolls_back(self):
        from postgres_storage import migrate_postgres
        engine, connection = MagicMock(), MagicMock()
        engine.connect.return_value = connection
        connection.execute.return_value.scalars.return_value.all.return_value = []
        inspector = MagicMock(); inspector.get_table_names.return_value = []
        with patch('postgres_storage.inspect', return_value=inspector), patch('postgres_storage.audit_connection', side_effect=DatabasePolicyError('api_privileges')):
            with self.assertRaises(DatabaseStageError) as caught:
                migrate_postgres(engine, MetaData())
        result = diagnostic(caught.exception)
        self.assertEqual(result['stage'], 'security_verification')
        self.assertEqual(result['policy_code'], 'api_privileges')
        self.assertEqual(connection.begin.return_value.__exit__.call_args.args[0], DatabaseStageError)
        connection.close.assert_called_once()

    def test_successful_cli_output_and_exit_code(self):
        import manage_database
        engine = MagicMock(); stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(manage_database, 'load_backend', return_value=(engine, MetaData())), patch.object(manage_database, 'execute_operation', return_value={'rls': 'enabled'}), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(manage_database.main(['verify']), 0)
        self.assertEqual(json.loads(stdout.getvalue()), {'rls': 'enabled'})
        self.assertEqual(stderr.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
