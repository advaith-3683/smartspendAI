"""Explicit private-schema PostgreSQL migrations and fail-closed privilege audit.

No Supabase Auth, auth.uid policies, public-schema DDL or managed-schema writes.
The backend uses its existing sessions/ownership checks with a server-only DB role.
"""
import os
import time
from sqlalchemy import MetaData, inspect, text
from database_diagnostics import DatabasePolicyError, database_stage

SCHEMA = 'smartspend'
VERSION = 5
API_ROLES = ('anon', 'authenticated', 'service_role')


def private_metadata(metadata):
    result = MetaData(schema=SCHEMA)
    for table in metadata.sorted_tables:
        table.to_metadata(result, schema=SCHEMA)
    return result


def audit_connection(connection, metadata, deadline=None):
    def execute(statement, parameters=None):
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("Database security verification deadline exceeded")
        result = connection.execute(statement, parameters) if parameters is not None else connection.execute(statement)
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("Database security verification deadline exceeded")
        return result

    expected = {table.name for table in metadata.sorted_tables} | {'smartspend_schema'}
    rows = execute(text('''
        SELECT c.oid, c.relname, c.relrowsecurity, c.relforcerowsecurity,
               c.relowner = (SELECT oid FROM pg_roles WHERE rolname=current_user) AS owned,
               r.rolbypassrls OR r.rolsuper AS bypass
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        CROSS JOIN pg_roles r
        WHERE n.nspname=:schema AND c.relkind IN ('r','p') AND r.rolname=current_user
    '''), {'schema': SCHEMA}).mappings().all()
    if {row['relname'] for row in rows} != expected:
        raise DatabasePolicyError('missing_tables')
    public_access = execute(text('''
        SELECT EXISTS (
          SELECT 1 FROM pg_namespace n,
          LATERAL aclexplode(COALESCE(n.nspacl, acldefault('n', n.nspowner))) a
          WHERE n.nspname=:schema AND a.grantee=0
        ) OR EXISTS (
          SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace,
          LATERAL aclexplode(COALESCE(c.relacl, acldefault(
             CASE WHEN c.relkind='S' THEN 'S'::"char" ELSE 'r'::"char" END, c.relowner))) a
          WHERE n.nspname=:schema AND c.relkind IN ('r','p','S') AND a.grantee=0
        ) OR EXISTS (
          SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
          JOIN pg_attribute attribute ON attribute.attrelid=c.oid,
          LATERAL aclexplode(attribute.attacl) a
          WHERE n.nspname=:schema AND a.grantee=0
        )
    '''), {'schema': SCHEMA}).scalar()
    if public_access:
        raise DatabasePolicyError('public_privileges')
    policies = execute(text('SELECT count(*) FROM pg_policies WHERE schemaname=:schema'), {'schema': SCHEMA}).scalar()
    if policies:
        raise DatabasePolicyError('unexpected_policies')
    roles = execute(text('SELECT rolname FROM pg_roles WHERE rolname IN (\'anon\',\'authenticated\',\'service_role\')')).scalars().all()
    for row in rows:
        if not row['relrowsecurity']:
            raise DatabasePolicyError('rls_disabled')
        if not row['bypass'] and (not row['owned'] or row['relforcerowsecurity']):
            raise DatabasePolicyError('backend_rls_access')
        # These table OIDs came from a completed catalog fetch into Python.
        # The privilege call is a separate bound query, not an optimizer-inlined
        # subquery relying on a relkind predicate in the same SQL expression.
        for role in roles:
            access = execute(text('''
                SELECT has_schema_privilege(:role, :schema, 'USAGE,CREATE')
                    OR has_table_privilege(:role, CAST(:oid AS oid), 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                    OR has_any_column_privilege(:role, CAST(:oid AS oid), 'SELECT,INSERT,UPDATE,REFERENCES')
            '''), {'role': role, 'schema': SCHEMA, 'oid': row['oid']}).scalar()
            if access:
                raise DatabasePolicyError('api_privileges')
    for role in roles:
        sequence_access = execute(text('''
            SELECT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname=:schema AND c.relkind='S'
             -- WHERE predicates can be reordered; guard the object-specific call.
             AND CASE WHEN c.relkind = 'S'
                      THEN has_sequence_privilege(:role, c.oid, 'USAGE,SELECT,UPDATE')
                      ELSE false
                 END)
        '''), {'role': role, 'schema': SCHEMA}).scalar()
        if sequence_access:
            raise DatabasePolicyError('sequence_privileges')
    version = execute(text('SELECT version FROM smartspend.smartspend_schema')).scalars().all()
    if version != [VERSION]:
        raise DatabasePolicyError('schema_version')
    return {'schema': SCHEMA, 'version': VERSION, 'tables_checked': len(rows),
            'api_roles_checked': roles, 'rls': 'enabled, no policies', 'public_access': False}


def lock_and_check_empty_v4(connection, private, existing):
    """Narrow backup exemption: complete v4 only, writer locks held to commit.

    Never trust a prior read-only observation or rows hidden by RLS.
    Older versions and unexpected/partial schemas still require a backup.
    """
    legacy = {table.name for table in private.sorted_tables} - {'email_accounts'}
    if existing != legacy | {'smartspend_schema'}:
        return False
    connection.execute(text("SET LOCAL lock_timeout = '10s'"))
    quoted = connection.dialect.identifier_preparer.quote_identifier
    names = ', '.join('smartspend.' + quoted(name) for name in sorted(existing))
    connection.execute(text('LOCK TABLE ' + names + ' IN SHARE ROW EXCLUSIVE MODE'))
    # Re-read the marker after acquiring the table locks.
    if connection.execute(text('SELECT version FROM smartspend.smartspend_schema')).scalars().all() != [4]:
        return False
    visible = connection.execute(text('''
        SELECT c.relname, (r.rolsuper OR r.rolbypassrls OR
               (c.relowner=r.oid AND NOT c.relforcerowsecurity)) AS full_visibility
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        CROSS JOIN pg_roles r
        WHERE n.nspname=:schema AND c.relkind IN ('r','p') AND r.rolname=current_user
    '''), {'schema': SCHEMA}).mappings().all()
    if {row['relname'] for row in visible} != existing or not all(row['full_visibility'] for row in visible):
        return False
    for name in sorted(legacy):
        if connection.execute(text('SELECT EXISTS (SELECT 1 FROM smartspend.' + quoted(name) + ')')).scalar_one():
            return False
    return True


def migrate_postgres(engine, metadata):
    with database_stage('migration'):
        private = private_metadata(metadata)
    with database_stage('connection'):
        connection = engine.connect()
    try:
        with database_stage('migration'), connection.begin():
            # Emptiness must see writers committed before our table locks, even
            # when a server/session default uses repeatable-read isolation.
            connection.execute(text('SET TRANSACTION ISOLATION LEVEL READ COMMITTED'))
            connection.execute(text('SELECT pg_advisory_xact_lock(71480321)'))
            connection.execute(text('CREATE SCHEMA IF NOT EXISTS smartspend'))
            existing = set(inspect(connection).get_table_names(schema=SCHEMA))
            expected = {table.name for table in private.sorted_tables} | {'smartspend_schema'}
            if existing - expected or (existing and 'smartspend_schema' not in existing):
                raise DatabasePolicyError('unversioned_schema')
            if 'smartspend_schema' in existing:
                versions = connection.execute(text('SELECT version FROM smartspend.smartspend_schema')).scalars().all()
                if versions not in ([2], [3], [4], [5]):
                    raise DatabasePolicyError('schema_version')
                if versions != [VERSION] and os.getenv('POSTGRES_BACKUP_CONFIRMED') != 'true':
                    if versions != [4] or not lock_and_check_empty_v4(connection, private, existing):
                        raise DatabasePolicyError('backup_required')
            # Only this dedicated schema is affected. Supabase-managed schemas stay untouched.
            private.create_all(connection)
            connection.execute(text('CREATE TABLE IF NOT EXISTS smartspend.smartspend_schema (version INTEGER PRIMARY KEY)'))
            connection.execute(text('DELETE FROM smartspend.smartspend_schema WHERE version < 5'))
            connection.execute(text('INSERT INTO smartspend.smartspend_schema VALUES (5) ON CONFLICT DO NOTHING'))
            roles = connection.execute(text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated','service_role')")).scalars().all()
            grantees = 'PUBLIC' + ''.join(', "' + role + '"' for role in roles)
            connection.execute(text('REVOKE ALL ON SCHEMA smartspend FROM ' + grantees))
            connection.execute(text('REVOKE ALL ON ALL TABLES IN SCHEMA smartspend FROM ' + grantees))
            connection.execute(text('REVOKE ALL ON ALL SEQUENCES IN SCHEMA smartspend FROM ' + grantees))
            connection.execute(text('ALTER DEFAULT PRIVILEGES IN SCHEMA smartspend REVOKE ALL ON TABLES FROM ' + grantees))
            connection.execute(text('ALTER DEFAULT PRIVILEGES IN SCHEMA smartspend REVOKE ALL ON SEQUENCES FROM ' + grantees))
            for name in sorted(expected):
                quoted = connection.dialect.identifier_preparer.quote(name)
                connection.execute(text(f'ALTER TABLE smartspend.{quoted} ENABLE ROW LEVEL SECURITY'))
            with database_stage('security_verification'):
                result = audit_connection(connection, private)
        return result
    finally:
        with database_stage('connection'):
            connection.close()


def verify_postgres(engine, metadata):
    with database_stage('connection'):
        connection = engine.connect()
    try:
        with database_stage('security_verification'):
            connection.execute(text("SET LOCAL statement_timeout = '15s'"))
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            return audit_connection(connection, metadata, deadline=time.monotonic() + 45)
    finally:
        with database_stage('connection'):
            connection.close()
