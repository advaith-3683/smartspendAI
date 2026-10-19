"""Opt-in REAL PostgreSQL tests. Never uses DATABASE_URL as its test target.

Use only a disposable dedicated database with SMARTSPEND_TEST_POSTGRES_URL and
SMARTSPEND_TEST_POSTGRES_CONFIRM=disposable-smartspend-database. Does not drop data.
"""
import os
import unittest

TEST_URL = os.getenv('SMARTSPEND_TEST_POSTGRES_URL')
CONFIRMED = os.getenv('SMARTSPEND_TEST_POSTGRES_CONFIRM') == 'disposable-smartspend-database'


@unittest.skipUnless(TEST_URL and CONFIRMED, 'No explicitly confirmed isolated PostgreSQL test database supplied')
class RealPostgresTests(unittest.TestCase):
    def isolated_engine(self):
        from database import build_engine
        engine = build_engine(TEST_URL)
        if engine.dialect.name != 'postgresql':
            self.fail('Isolated integration URL must select PostgreSQL')
        from sqlalchemy.engine import make_url
        configured = os.getenv('DATABASE_URL', '')
        if configured.startswith(('postgres:', 'postgresql:','postgresql+psycopg:')):
            configured_url, test_url = make_url(configured), make_url(TEST_URL)
            def identity(url):
                # Shared Supabase pooler hosts route different projects by username.
                project = (url.username or '').rsplit('.', 1)[-1] if (url.host or '').endswith('.pooler.supabase.com') else None
                return (url.host, url.port, url.database, project)
            if identity(configured_url) == identity(test_url):
                self.fail('Refusing to test the configured application database; supply a separate disposable database')
        return engine

    def test_private_tables_security_and_persistence(self):
        from sqlalchemy import select, func, text
        from database import Base, build_engine
        import models, auth
        from postgres_storage import private_metadata, migrate_postgres, verify_postgres
        from decimal import Decimal
        import uuid
        engine = self.isolated_engine()
        tables = private_metadata(Base.metadata)
        try:
            first = migrate_postgres(engine, tables)
            self.assertFalse(first['public_access'])
            self.assertEqual(first, migrate_postgres(engine, tables))
            self.assertEqual(first, verify_postgres(engine, tables))
            users = tables.tables['smartspend.users']
            unique = 'isolated-' + uuid.uuid4().hex
            with engine.begin() as connection:
                uid = connection.execute(users.insert().values(name=unique, monthly_income=Decimal('123.45')).returning(users.c.id)).scalar_one()
                roles = connection.execute(text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated')")).scalars().all()
            engine.dispose()
            with engine.connect() as connection:
                self.assertEqual(connection.execute(select(users.c.monthly_income).where(users.c.id == uid)).scalar_one(), Decimal('123.45'))
                # Validate effective denial under actual API roles, not only an RLS flag.
                if not roles:
                    self.fail('Isolated database must provide anon/authenticated roles for real privilege-denial tests')
                for role in roles:
                    for operation in ('SELECT * FROM smartspend.users LIMIT 1', "INSERT INTO smartspend.users (name,monthly_income) VALUES ('denied', 1)", 'UPDATE smartspend.users SET monthly_income=1 WHERE false', 'DELETE FROM smartspend.users WHERE false'):
                        transaction = connection.begin_nested()
                        try:
                            connection.execute(text('SET LOCAL ROLE "' + role + '"'))
                            from sqlalchemy.exc import DBAPIError
                            with self.assertRaises(DBAPIError):
                                connection.execute(text(operation))
                        finally:
                            transaction.rollback()
        finally:
            engine.dispose()

    def test_email_constraints_and_preserved_user_values(self):
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError
        from database import Base
        import models, auth, uuid
        from postgres_storage import private_metadata, migrate_postgres, verify_postgres
        engine = self.isolated_engine()
        try:
            migrate_postgres(engine, Base.metadata)
            tables = private_metadata(Base.metadata).tables
            users, emails = tables['smartspend.users'], tables['smartspend.email_accounts']
            # All fixture writes roll back, including the duplicate constraint probes.
            with engine.connect() as connection:
                transaction = connection.begin()
                try:
                    ids = [connection.execute(users.insert().values(name='same name', monthly_income=12345).returning(users.c.id)).scalar_one() for _ in range(2)]
                    email = uuid.uuid4().hex + '+tag@example.com'
                    connection.execute(emails.insert().values(user_id=ids[0], email=email, password_hash='synthetic-only'))
                    for candidate in (email, email.upper()):
                        savepoint = connection.begin_nested()
                        try:
                            with self.assertRaises(IntegrityError):
                                connection.execute(emails.insert().values(user_id=ids[1], email=candidate, password_hash='synthetic-only'))
                        finally:
                            savepoint.rollback()
                    self.assertEqual(connection.execute(users.select().with_only_columns(users.c.monthly_income).where(users.c.id == ids[0])).scalar_one(), 12345)
                    self.assertFalse(verify_postgres(engine, Base.metadata)['public_access'])
                finally:
                    transaction.rollback()
        finally:
            engine.dispose()

    def test_mixed_relations_and_forbidden_sequence_privileges(self):
        from sqlalchemy import text
        from database import Base
        import models, auth
        from postgres_storage import private_metadata, migrate_postgres, verify_postgres, audit_connection
        from database_diagnostics import DatabasePolicyError, database_stage
        engine = self.isolated_engine()
        metadata = private_metadata(Base.metadata)
        try:
            # Migration calls the real audit inside its transaction. Fresh app DDL
            # supplies ordinary tables plus SERIAL sequences in this isolated DB.
            migrate_postgres(engine, metadata)
            self.assertFalse(verify_postgres(engine, metadata)['public_access'])
            with database_stage('security_verification'), engine.connect() as connection:
                with connection.begin():
                    objects = connection.execute(text("SELECT c.relkind, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:schema AND c.relkind IN ('r','S')"), {'schema': 'smartspend'}).all()
                    self.assertTrue(any(kind == 'r' for kind, _ in objects))
                    sequences = [name for kind, name in objects if kind == 'S']
                    self.assertTrue(sequences, 'Isolated fixture must contain sequences')
                    self.assertTrue(connection.execute(text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon')")).scalar(), 'Isolated fixture requires the anon API role')
                    audit_connection(connection, metadata)  # Must not raise WrongObjectType.
                    # Grant only within a savepoint, then restore permissions even
                    # if the assertion/audit fails. No production role is created.
                    savepoint = connection.begin_nested()
                    try:
                        identifier = connection.dialect.identifier_preparer.quote(sequences[0])
                        connection.execute(text(f'GRANT USAGE ON SEQUENCE smartspend.{identifier} TO anon'))
                        with self.assertRaises(DatabasePolicyError) as caught:
                            audit_connection(connection, metadata)
                        self.assertEqual(caught.exception.code, 'sequence_privileges')
                    finally:
                        savepoint.rollback()
                    self.assertFalse(audit_connection(connection, metadata)['public_access'])
            self.assertFalse(verify_postgres(engine, metadata)['public_access'])
        finally:
            engine.dispose()


if __name__ == '__main__':
    unittest.main()
