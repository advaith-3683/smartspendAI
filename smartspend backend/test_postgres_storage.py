"""Offline PostgreSQL configuration/DDL tests; no database connections."""
import unittest
from unittest.mock import patch
from sqlalchemy import MetaData, Column, Integer, Table
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.schema import CreateTable
import test_environment  # Must precede database import, even under full discovery.
from database import build_engine
from postgres_storage import private_metadata, audit_connection


class PostgresOfflineTests(unittest.TestCase):
    def test_migration_backup_gate_and_empty_upgrade_audit_rollback(self):
        import os
        from unittest.mock import MagicMock
        from postgres_storage import migrate_postgres
        from database_diagnostics import DatabasePolicyError, DatabaseStageError
        for version, empty, audit_failure in ((4, True, False), (4, False, False), (2, True, False), (3, True, False), (5, False, False), (4, True, True)):
            with self.subTest(version=version, empty=empty, audit_failure=audit_failure):
                metadata = MetaData()
                Table('users', metadata, Column('id', Integer, primary_key=True))
                engine, connection, inspector = MagicMock(), MagicMock(), MagicMock()
                engine.connect.return_value = connection
                inspector.get_table_names.return_value = ['users', 'smartspend_schema']
                def execute(statement, *args):
                    result = MagicMock()
                    result.scalars.return_value.all.return_value = [version] if 'SELECT version' in str(statement) else []
                    return result
                connection.execute.side_effect = execute
                blocked = version in (2, 3) or (version == 4 and not empty)
                with patch.dict(os.environ, {'POSTGRES_BACKUP_CONFIRMED': ''}), patch('postgres_storage.private_metadata', return_value=metadata), patch('postgres_storage.inspect', return_value=inspector), patch('postgres_storage.lock_and_check_empty_v4', return_value=empty) as exemption, patch.object(metadata, 'create_all') as ddl, patch('postgres_storage.audit_connection', side_effect=DatabasePolicyError('api_privileges') if audit_failure else None, return_value={'version': 5}) as audit:
                    if blocked or audit_failure:
                        with self.assertRaises(DatabaseStageError):
                            migrate_postgres(engine, metadata)
                        self.assertIsNotNone(connection.begin.return_value.__exit__.call_args.args[0])
                    else:
                        self.assertEqual(migrate_postgres(engine, metadata), {'version': 5})
                    if version == 4: exemption.assert_called_once()
                    else: exemption.assert_not_called()
                    if blocked:
                        ddl.assert_not_called()
                        audit.assert_not_called()
                    else:
                        ddl.assert_called_once_with(connection)
                        audit.assert_called_once()
                statements = [str(call.args[0]) for call in connection.execute.call_args_list]
                self.assertEqual(statements[0], 'SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
                connection.close.assert_called_once()

    def test_empty_v4_exemption_holds_writer_locks_and_checks_every_table(self):
        from unittest.mock import MagicMock
        from postgres_storage import lock_and_check_empty_v4
        metadata = MetaData()
        for name in ('users', 'auth_sessions', 'transactions', 'email_accounts'):
            Table(name, metadata, Column('id', Integer, primary_key=True))
        existing = {'users', 'auth_sessions', 'transactions', 'smartspend_schema'}
        for populated, visibility, version, expected in ((False, True, [4], True), (True, True, [4], False), (False, False, [4], False), (False, True, [5], False)):
            connection = MagicMock()
            connection.dialect = dialect()
            def execute(statement, *args):
                sql = str(statement)
                result = MagicMock()
                result.scalars.return_value.all.return_value = version
                result.mappings.return_value.all.return_value = [{'relname': n, 'full_visibility': visibility} for n in existing]
                result.scalar_one.return_value = populated
                return result
            connection.execute.side_effect = execute
            self.assertEqual(lock_and_check_empty_v4(connection, metadata, existing), expected)
            calls = [str(call.args[0]) for call in connection.execute.call_args_list]
            self.assertIn('SHARE ROW EXCLUSIVE MODE', calls[1])
            self.assertIn('"auth_sessions"', calls[1])
            self.assertIn('"transactions"', calls[1])
            if expected:
                self.assertEqual(sum('SELECT EXISTS' in sql for sql in calls), 3)

    def test_empty_v4_exemption_refuses_partial_or_unexpected_schema(self):
        from unittest.mock import MagicMock
        from postgres_storage import lock_and_check_empty_v4
        metadata = MetaData()
        Table('users', metadata, Column('id', Integer, primary_key=True))
        for existing in ({'smartspend_schema'}, {'users', 'smartspend_schema', 'unexpected'}):
            connection = MagicMock()
            self.assertFalse(lock_and_check_empty_v4(connection, metadata, existing))
            connection.execute.assert_not_called()

    def test_empty_v4_lock_failure_is_not_ignored(self):
        from unittest.mock import MagicMock
        from postgres_storage import lock_and_check_empty_v4
        metadata = MetaData()
        Table('users', metadata, Column('id', Integer, primary_key=True))
        connection = MagicMock()
        connection.dialect = dialect()
        connection.execute.side_effect = [MagicMock(), RuntimeError('synthetic lock timeout')]
        with self.assertRaises(RuntimeError):
            lock_and_check_empty_v4(connection, metadata, {'users', 'smartspend_schema'})

    def test_pooler_settings_and_driver(self):
        with patch('database.create_engine') as factory:
            build_engine('postgresql://postgres.example:placeholder@aws-0-us-west-2.pooler.supabase.com:5432/postgres?sslmode=require')
            args, options = factory.call_args
            self.assertEqual(args[0].drivername, 'postgresql+psycopg')
            self.assertTrue(options['pool_pre_ping'])
            self.assertEqual(options['pool_size'] + options['max_overflow'], 5)
            self.assertEqual(options['pool_timeout'], 10)
            self.assertEqual(options['pool_recycle'], 300)
            self.assertEqual(options['connect_args']['connect_timeout'], 15)
            self.assertNotIn('check_same_thread', options['connect_args'])
            self.assertTrue(options['hide_parameters'])

    def test_pooler_rejects_transaction_port_and_missing_tls(self):
        for suffix in (':6543/postgres?sslmode=require', ':5432/postgres'):
            with self.assertRaises(RuntimeError):
                build_engine('postgresql+psycopg://postgres.example:placeholder@aws-0-us-west-2.pooler.supabase.com' + suffix)
        with self.assertRaises(RuntimeError):
            build_engine('postgresql+psycopg2://placeholder@localhost/test')

    def test_metadata_targets_only_private_schema(self):
        # Import models only; does not import main or run migrations.
        import models, auth
        from database import Base
        cloned = private_metadata(Base.metadata)
        for table in cloned.sorted_tables:
            self.assertEqual(table.schema, 'smartspend')
            ddl = str(CreateTable(table).compile(dialect=dialect()))
            self.assertIn('smartspend.', ddl)
            self.assertNotIn('public.', ddl)
            self.assertNotIn('auth.', ddl)
            for fk in table.foreign_keys:
                self.assertEqual(fk.column.table.schema, 'smartspend')

    def test_audit_fails_closed_for_missing_tables(self):
        metadata = MetaData()
        Table('example', metadata, Column('id', Integer, primary_key=True))
        from unittest.mock import MagicMock
        connection = MagicMock()
        connection.execute.return_value.mappings.return_value.all.return_value = []
        with self.assertRaisesRegex(RuntimeError, 'missing or unexpected'):
            audit_connection(connection, metadata)

    def test_rls_flag_does_not_mask_public_privileges(self):
        from unittest.mock import MagicMock
        metadata = MetaData()
        Table('example', metadata, Column('id', Integer, primary_key=True))
        connection = MagicMock()
        catalog = MagicMock()
        catalog.mappings.return_value.all.return_value = [
            {'relname': name, 'oid': index, 'relrowsecurity': True, 'relforcerowsecurity': False, 'owned': True, 'bypass': False}
            for index, name in enumerate(('example', 'smartspend_schema'))]
        privileges = MagicMock(); privileges.scalar.return_value = True
        connection.execute.side_effect = [catalog, privileges]
        with self.assertRaisesRegex(RuntimeError, 'PUBLIC'):
            audit_connection(connection, metadata)

    def test_malformed_url_error_does_not_echo_input(self):
        with self.assertRaises(RuntimeError) as error:
            build_engine('postgresql+psycopg://user:placeholder@host:invalid-secret-port/db')
        self.assertNotIn('placeholder', str(error.exception))
        self.assertNotIn('invalid-secret-port', str(error.exception))

    def test_sequence_call_is_case_guarded_with_bound_filters(self):
        from unittest.mock import MagicMock
        metadata = MetaData()
        Table('example', metadata, Column('id', Integer, primary_key=True))
        connection = MagicMock()
        catalog = MagicMock()
        catalog.mappings.return_value.all.return_value = [
            {'relname': name, 'oid': index, 'relrowsecurity': True, 'relforcerowsecurity': False, 'owned': True, 'bypass': False}
            for index, name in enumerate(('example', 'smartspend_schema'), 10)]
        def scalar(value):
            result = MagicMock(); result.scalar.return_value = value
            return result
        roles = MagicMock(); roles.scalars.return_value.all.return_value = ['anon']
        version = MagicMock(); version.scalars.return_value.all.return_value = [5]
        connection.execute.side_effect = [catalog, scalar(False), scalar(0), roles,
                                          scalar(False), scalar(False), scalar(False), version]
        self.assertFalse(audit_connection(connection, metadata)['public_access'])
        statement, bindings = connection.execute.call_args_list[-2].args
        sql = str(statement)
        self.assertRegex(sql, r"(?s)CASE WHEN c\.relkind = 'S'\s+THEN has_sequence_privilege\(:role, c\.oid, 'USAGE,SELECT,UPDATE'\)\s+ELSE false\s+END")
        self.assertIn("n.nspname=:schema AND c.relkind='S'", sql)
        self.assertEqual(bindings, {'role': 'anon', 'schema': 'smartspend'})

    def test_forbidden_sequence_privileges_still_fail_audit(self):
        from unittest.mock import MagicMock
        from database_diagnostics import DatabasePolicyError
        metadata = MetaData()
        Table('example', metadata, Column('id', Integer, primary_key=True))
        connection = MagicMock()
        catalog = MagicMock()
        catalog.mappings.return_value.all.return_value = [
            {'relname': name, 'oid': index, 'relrowsecurity': True, 'relforcerowsecurity': False, 'owned': True, 'bypass': False}
            for index, name in enumerate(('example', 'smartspend_schema'), 10)]
        def scalar(value):
            result = MagicMock(); result.scalar.return_value = value
            return result
        roles = MagicMock(); roles.scalars.return_value.all.return_value = ['anon']
        connection.execute.side_effect = [catalog, scalar(False), scalar(0), roles,
                                          scalar(False), scalar(False), scalar(True)]
        with self.assertRaises(DatabasePolicyError) as caught:
            audit_connection(connection, metadata)
        self.assertEqual(caught.exception.code, 'sequence_privileges')


if __name__ == '__main__':
    unittest.main()
