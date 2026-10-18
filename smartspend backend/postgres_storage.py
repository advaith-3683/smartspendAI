"""Explicit private-schema PostgreSQL migrations and fail-closed privilege audit.

No Supabase Auth, auth.uid policies, public-schema DDL or managed-schema writes.
The backend uses its existing sessions/ownership checks with a server-only DB role.
"""
import os
from sqlalchemy import MetaData, inspect, text
from database_diagnostics import DatabasePolicyError, database_stage

SCHEMA = 'smartspend'
VERSION = 4
API_ROLES = ('anon', 'authenticated', 'service_role')


def private_metadata(metadata):
    result = MetaData(schema=SCHEMA)
    for table in metadata.sorted_tables:
        table.to_metadata(result, schema=SCHEMA)
    return result


def audit_connection(connection, metadata):
    expected = {table.name for table in metadata.sorted_tables} | {'smartspend_schema'}
    rows = connection.execute(text('''
        SELECT c.oid, c.relname, c.relrowsecurity, c.relforcerowsecurity,
               c.relowner = (SELECT oid FROM pg_roles WHERE rolname=current_user) AS owned,
               r.rolbypassrls OR r.rolsuper AS bypass
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        CROSS JOIN pg_roles r
        WHERE n.nspname=:schema AND c.relkind IN ('r','p') AND r.rolname=current_user
    '''), {'schema': SCHEMA}).mappings().all()
    if {row['relname'] for row in rows} != expected:
        raise DatabasePolicyError('missing_tables')
    public_access = connection.execute(text('''
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
    policies = connection.execute(text('SELECT count(*) FROM pg_policies WHERE schemaname=:schema'), {'schema': SCHEMA}).scalar()
    if policies:
        raise DatabasePolicyError('unexpected_policies')
    roles = connection.execute(text('SELECT rolname FROM pg_roles WHERE rolname IN (\'anon\',\'authenticated\',\'service_role\')')).scalars().all()
    for row in rows:
        if not row['relrowsecurity']:
            raise DatabasePolicyError('rls_disabled')
        if not row['bypass'] and (not row['owned'] or row['relforcerowsecurity']):
            raise DatabasePolicyError('backend_rls_access')
        for role in roles:
            access = connection.execute(text('''
                SELECT has_schema_privilege(:role, :schema, 'USAGE,CREATE')
                    OR has_table_privilege(:role, CAST(:oid AS oid), 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                    OR has_any_column_privilege(:role, CAST(:oid AS oid), 'SELECT,INSERT,UPDATE,REFERENCES')
            '''), {'role': role, 'schema': SCHEMA, 'oid': row['oid']}).scalar()
            if access:
                raise DatabasePolicyError('api_privileges')
    for role in roles:
        sequence_access = connection.execute(text('''
            SELECT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname=:schema AND c.relkind='S'
             AND has_sequence_privilege(:role, c.oid, 'USAGE,SELECT,UPDATE'))
        '''), {'role': role, 'schema': SCHEMA}).scalar()
        if sequence_access:
            raise DatabasePolicyError('sequence_privileges')
    version = connection.execute(text('SELECT version FROM smartspend.smartspend_schema')).scalars().all()
    if version != [VERSION]:
        raise DatabasePolicyError('schema_version')
    return {'schema': SCHEMA, 'version': VERSION, 'tables_checked': len(rows),
            'api_roles_checked': roles, 'rls': 'enabled, no policies', 'public_access': False}


def migrate_postgres(engine, metadata):
    with database_stage('migration'):
        private = private_metadata(metadata)
    with database_stage('connection'):
        connection = engine.connect()
    try:
        with database_stage('migration'), connection.begin():
            connection.execute(text('SELECT pg_advisory_xact_lock(71480321)'))
            connection.execute(text('CREATE SCHEMA IF NOT EXISTS smartspend'))
            existing = set(inspect(connection).get_table_names(schema=SCHEMA))
            expected = {table.name for table in private.sorted_tables} | {'smartspend_schema'}
            if existing - expected or (existing and 'smartspend_schema' not in existing):
                raise DatabasePolicyError('unversioned_schema')
            if 'smartspend_schema' in existing:
                versions = connection.execute(text('SELECT version FROM smartspend.smartspend_schema')).scalars().all()
                if versions not in ([2], [3], [4]):
                    raise DatabasePolicyError('schema_version')
                if versions != [VERSION] and os.getenv('POSTGRES_BACKUP_CONFIRMED') != 'true':
                    raise DatabasePolicyError('backup_required')
            # Only this dedicated schema is affected. Supabase-managed schemas stay untouched.
            private.create_all(connection)
            connection.execute(text('CREATE TABLE IF NOT EXISTS smartspend.smartspend_schema (version INTEGER PRIMARY KEY)'))
            connection.execute(text('DELETE FROM smartspend.smartspend_schema WHERE version < 4'))
            connection.execute(text('INSERT INTO smartspend.smartspend_schema VALUES (4) ON CONFLICT DO NOTHING'))
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
            return audit_connection(connection, metadata)
    finally:
        with database_stage('connection'):
            connection.close()
