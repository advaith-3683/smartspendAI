"""Operator-only offline SQLite -> empty PostgreSQL transfer. Never mutates source."""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
from sqlalchemy import create_engine, select, text, func, Integer
from database import build_engine, Base
import models
import auth
from migrations import migrate
from postgres_storage import SCHEMA, verify_postgres


def main():
    parser = argparse.ArgumentParser(description='Stop the backend, set DATABASE_URL to hosted PostgreSQL, then transfer an existing SQLite ledger.')
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    target = build_engine()
    if target.dialect.name != 'postgresql':
        raise SystemExit('DATABASE_URL must select PostgreSQL. No records transferred.')
    # Back up source independently before migrating a private working copy.
    from datetime import datetime, timezone
    backup = source.with_name(source.name + '.backup-transfer-' + datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f'))
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(backup)) as dest:
        src.backup(dest)
    with tempfile.TemporaryDirectory() as directory:
        working = Path(directory) / 'transfer.db'
        with closing(sqlite3.connect(backup)) as src, closing(sqlite3.connect(working)) as dest:
            src.backup(dest)
        original = create_engine('sqlite:///' + working.as_posix())
        try:
            migrate(original, Base.metadata)
            # Target DDL/privilege hardening must be performed separately first.
            verify_postgres(target, Base.metadata)
            with original.connect().execution_options(schema_translate_map={SCHEMA: None}) as src, target.begin() as dest:
                dest.execute(text("SELECT pg_advisory_xact_lock(71480321)"))
                dest.execute(text("SET LOCAL TIME ZONE 'UTC'"))
                # Stop writers first; table locks also prevent an accidental concurrent signup.
                names = ", ".join(dest.dialect.identifier_preparer.format_table(t) for t in Base.metadata.sorted_tables)
                dest.execute(text("LOCK TABLE " + names + " IN ACCESS EXCLUSIVE MODE"))
                # All-or-nothing insertion, refuse merges/overwrites.
                for table in Base.metadata.sorted_tables:
                    if dest.execute(select(table).limit(1)).first():
                        raise RuntimeError('Target database is not empty; transfer refused')
                for table in Base.metadata.sorted_tables:
                    count = 0
                    result = src.execute(select(table))
                    while batch := result.mappings().fetchmany(500):
                        dest.execute(table.insert(), [dict(row) for row in batch])
                        count += len(batch)
                    if 'id' in table.c and isinstance(table.c.id.type, Integer):
                        # Table names come only from trusted metadata.
                        qualified = dest.dialect.identifier_preparer.format_table(table)
                        dest.execute(text(f"SELECT setval(pg_get_serial_sequence(:name, 'id'), COALESCE(MAX(id), 1), COUNT(*) > 0) FROM {qualified}"), {"name": qualified})
                    target_count = dest.execute(select(func.count()).select_from(table)).scalar()
                    if target_count != count:
                        raise RuntimeError('Transfer row-count mismatch')
                    # Compare every persisted column, including IDs, cents, credentials and history.
                    order = list(table.primary_key.columns)
                    left = src.execute(select(table).order_by(*order))
                    right = dest.execute(select(table).order_by(*order))
                    while True:
                        source_rows = left.fetchmany(500)
                        target_rows = right.fetchmany(500)
                        if not source_rows and not target_rows:
                            break
                        def canonical(rows):
                            from datetime import datetime, timezone
                            return [tuple((v.astimezone(timezone.utc).replace(tzinfo=None) if v.tzinfo else v) if isinstance(v, datetime) else v for v in row) for row in rows]
                        if canonical(source_rows) != canonical(target_rows):
                            raise RuntimeError('Transfer value validation mismatch')
                    print(f'{table.name}: {count} records copied and validated (commit pending)')
        finally:
            original.dispose(); target.dispose()
    print('Transfer committed. Source and pre-transfer backup retained. Verify account login and record totals before changing any deployment.')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Transfer failed; target insertion rolled back. Source retained. Check database connectivity, permissions and empty-target requirements without sharing secrets.')
