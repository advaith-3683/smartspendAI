"""Operator command with sanitized, stage-specific stderr diagnostics."""
import argparse
import json
import sys
from database_diagnostics import DatabasePolicyError, database_stage, diagnostic_json


def load_backend():
    # Configuration/driver/import errors must also pass through sanitization.
    from database import engine, Base
    import models
    import auth
    return engine, Base.metadata


def execute_operation(engine, metadata, action):
    from postgres_storage import migrate_postgres, verify_postgres
    if engine.dialect.name != 'postgresql':
        raise DatabasePolicyError('postgres_required')
    return migrate_postgres(engine, metadata) if action == 'migrate' else verify_postgres(engine, metadata)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Initialize/audit SmartSpend private PostgreSQL tables. No source-data transfer.')
    parser.add_argument('action', choices=('migrate', 'verify'))
    args = parser.parse_args(argv)
    engine = None
    status = 0
    try:
        with database_stage('connection'):
            engine, metadata = load_backend()
        with database_stage('migration' if args.action == 'migrate' else 'security_verification'):
            result = execute_operation(engine, metadata, args.action)
        print(json.dumps(result, sort_keys=True))
    except Exception as error:
        print(diagnostic_json(error), file=sys.stderr)
        status = 1
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception as error:
                print(diagnostic_json(error, 'connection'), file=sys.stderr)
                status = 1
    return status


if __name__ == '__main__':
    raise SystemExit(main())
