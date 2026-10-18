"""Operator command. Credentials come from DATABASE_URL, never CLI arguments."""
import argparse
import json
from database import engine, Base
import models
import auth
from postgres_storage import migrate_postgres, verify_postgres


def main():
    parser = argparse.ArgumentParser(description='Initialize/audit SmartSpend private PostgreSQL tables. No source-data transfer.')
    parser.add_argument('action', choices=('migrate', 'verify'))
    args = parser.parse_args()
    if engine.dialect.name != 'postgresql':
        raise SystemExit('This command requires PostgreSQL DATABASE_URL. SQLite was not changed.')
    try:
        result = migrate_postgres(engine, Base.metadata) if args.action == 'migrate' else verify_postgres(engine, Base.metadata)
        print(json.dumps(result, sort_keys=True))
    except RuntimeError as exc:
        raise SystemExit(str(exc))
    except Exception:
        raise SystemExit('Database operation failed. Check URI encoding, TLS, connectivity and role permissions. Credentials and SQL parameters are not printed.')
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
