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


if __name__ == '__main__':
    unittest.main()
