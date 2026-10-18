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
    def test_private_tables_security_and_persistence(self):
        from sqlalchemy import select, func, text
        from database import Base, build_engine
        import models, auth
        from postgres_storage import private_metadata, migrate_postgres, verify_postgres
        from decimal import Decimal
        import uuid
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


if __name__ == '__main__':
    unittest.main()
