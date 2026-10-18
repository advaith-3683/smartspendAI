"""Durable SQL storage: stable local SQLite path or hosted PostgreSQL."""
import os
from database_diagnostics import DatabasePolicyError
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).with_name('.env'))
from sqlalchemy import create_engine, MetaData
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker, declarative_base

DEFAULT_PATH = Path(__file__).resolve().with_name('smartspend.db').as_posix()
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///' + DEFAULT_PATH)
if DATABASE_URL.startswith(('postgres://', 'postgresql://')):
    DATABASE_URL = 'postgresql+psycopg://' + DATABASE_URL.split('://', 1)[1]


def build_engine(url=DATABASE_URL):
    try:
        parsed = make_url(url)
        # Force port parsing here so malformed credentials cannot leak through an exception.
        parsed.port
    except Exception:
        raise DatabasePolicyError('invalid_url') from None
    if parsed.drivername in {'postgres', 'postgresql'}:
        parsed = parsed.set(drivername='postgresql+psycopg')
        url = parsed
    if parsed.get_backend_name() == 'postgresql' and parsed.drivername != 'postgresql+psycopg':
        raise DatabasePolicyError('driver_required')
    production = os.getenv('APP_ENV', 'development') == 'production'
    if parsed.get_backend_name() == 'sqlite':
        path = Path(parsed.database or '')
        if production:
            disk = os.getenv('PERSISTENT_DATA_DIR')
            if not disk or not path.is_absolute() or parsed.database == ':memory:':
                raise RuntimeError('Production SQLite requires an absolute DATABASE_URL on PERSISTENT_DATA_DIR; use hosted PostgreSQL otherwise')
            resolved = path.resolve()
            if not resolved.is_relative_to(Path(disk).resolve()):
                raise RuntimeError('SQLite database must be inside PERSISTENT_DATA_DIR')
            if not Path(disk).is_dir():
                raise RuntimeError('Persistent data directory is not mounted')
        return create_engine(url, connect_args={'check_same_thread': False, 'timeout': 30}, pool_pre_ping=True)
    if parsed.get_backend_name() != 'postgresql':
        raise RuntimeError('Supported databases: SQLite and PostgreSQL')
    supabase_pooler = (parsed.host or '').lower().endswith('.pooler.supabase.com')
    if supabase_pooler and parsed.port != 5432:
        raise DatabasePolicyError('session_pooler')
    if (production or supabase_pooler) and parsed.query.get('sslmode') not in {'require', 'verify-ca', 'verify-full'}:
        raise DatabasePolicyError('tls_required')
    return create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=2, pool_timeout=10, pool_recycle=300, hide_parameters=True, connect_args={'connect_timeout': 15, 'prepare_threshold': None})


engine = build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
APP_SCHEMA = 'smartspend' if engine.dialect.name == 'postgresql' else None
Base = declarative_base(metadata=MetaData(schema=APP_SCHEMA))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
