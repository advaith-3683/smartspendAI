"""Versioned additive schema migration with a SQLite online backup before changes."""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from contextlib import closing

def migrate(engine, metadata):
    if engine.dialect.name == "postgresql":
        from postgres_storage import migrate_postgres
        return migrate_postgres(engine, metadata)
    if engine.dialect.name != "sqlite":
        raise RuntimeError("Supported migration dialects: SQLite and PostgreSQL")
    path = Path(engine.url.database)
    # Serialize startup across processes before reading the schema version.
    # Money conversion, additive DDL and the version marker commit together.
    with engine.begin() as connection:
        connection = connection.execution_options(schema_translate_map={"smartspend": None})
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        version = connection.exec_driver_sql("PRAGMA user_version").scalar()
        if version > 4:
            raise RuntimeError("Database schema is newer than this application")
        existing = {row[0] for row in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")}
        if version < 4 and existing:
            backup = path.with_name(path.name + ".backup-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f"))
            # A reserved write lock still permits this independent read backup.
            with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(backup)) as target:
                source.backup(target)
        if version < 2:
            from decimal import Decimal, ROUND_HALF_UP
            for table, column in (("users", "monthly_income"), ("budgets", "monthly_limit"), ("transactions", "amount"), ("bills", "amount")):
                if table in existing:
                    rows = connection.exec_driver_sql(f"SELECT id, {column} FROM {table}").fetchall()
                    for row_id, value in rows:
                        money = Decimal(str(value))
                        if not money.is_finite() or abs(money) > Decimal("1000000000"):
                            raise RuntimeError("Legacy money out of bounds; operator review required")
                        cents = int((money * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
                        connection.exec_driver_sql(f"UPDATE {table} SET {column}=? WHERE id=?", (cents, row_id))
        metadata.create_all(connection)
        connection.exec_driver_sql("PRAGMA user_version = 4")
