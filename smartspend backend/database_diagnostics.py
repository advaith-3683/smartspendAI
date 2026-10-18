"""Structured database failures: fixed explanations, never driver error text."""
from contextlib import contextmanager
import json
import re
import socket
import ssl

POLICIES = {
    'missing_tables': 'Private application tables are missing or unexpected; run the explicit migration command',
    'public_privileges': 'PUBLIC has application schema/object privileges; security audit failed',
    'unexpected_policies': 'Unexpected RLS policies in private application schema; operator review required',
    'rls_disabled': 'An application table has RLS disabled; security audit failed',
    'backend_rls_access': 'Backend DB role cannot access deny-by-default RLS tables; use the server-only migration owner role',
    'api_privileges': 'A Supabase API role retains effective application access; security audit failed',
    'sequence_privileges': 'A Supabase API role retains sequence access; security audit failed',
    'schema_version': 'Unsupported application schema version',
    'unversioned_schema': 'Refusing an unexpected or unversioned private application schema',
    'backup_required': 'Back up the database, then set POSTGRES_BACKUP_CONFIRMED=true for an upgrade',
    'invalid_url': 'Invalid DATABASE_URL. Check URI structure and password percent-encoding without logging the URI.',
    'driver_required': 'PostgreSQL requires the postgresql+psycopg:// URL scheme (psycopg 3)',
    'tls_required': 'PostgreSQL requires TLS (sslmode=require or stronger). Do not disable TLS to retry.',
    'session_pooler': 'Use the Supabase Session pooler URI on port 5432, not transaction mode',
    'postgres_required': 'This operator command requires PostgreSQL. SQLite was not changed.',
}


class DatabasePolicyError(RuntimeError):
    def __init__(self, code):
        self.code = code if code in POLICIES else 'unknown_policy'
        super().__init__(POLICIES.get(self.code, 'Database configuration or security policy refused the operation.'))


class DatabaseStageError(Exception):
    def __init__(self, stage, original):
        self.stage = stage
        self.original = original
        super().__init__('Database stage failed')

    def __str__(self):
        return diagnostic_json(self)


@contextmanager
def database_stage(stage):
    try:
        yield
    except DatabaseStageError:
        raise
    except Exception as error:
        raise DatabaseStageError(stage, error) from None


def _chain(error):
    result, seen = [], set()
    while error is not None and id(error) not in seen and len(result) < 12:
        seen.add(id(error)); result.append(error)
        error = getattr(error, 'orig', None) or error.__cause__ or error.__context__
    return result


def _class_name(error):
    name = type(error).__name__
    return name if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}', name) else 'Exception'


def diagnostic(error, fallback_stage='connection'):
    stage = error.stage if isinstance(error, DatabaseStageError) else fallback_stage
    original = error.original if isinstance(error, DatabaseStageError) else error
    chain = _chain(original)
    state = None
    for item in chain:
        candidate = getattr(item, 'sqlstate', None) or getattr(item, 'pgcode', None)
        if isinstance(candidate, str) and re.fullmatch(r'[0-9A-Z]{5}', candidate):
            state = candidate
            break
    policy = next((item for item in chain if isinstance(item, DatabasePolicyError)), None)
    # Reading driver text is only for fixed category selection. It is NEVER emitted.
    def safe_hints(item):
        try:
            return str(item)[:8192].lower()
        except Exception:
            return ''
    hints = ' '.join(safe_hints(item) for item in chain)
    if policy:
        category = ('tls' if policy.code == 'tls_required' else ('security_audit' if stage == 'security_verification' else 'configuration_or_schema'))
        explanation = POLICIES.get(policy.code, 'Database configuration or security policy refused the operation.')
    elif state == '42501':
        category = 'insufficient_privileges'
        explanation = 'The database role lacks permission for this operation. Check ownership and CREATE/ALTER/REVOKE privileges for the private smartspend schema; do not bypass the audit.'
    elif state and (state.startswith('42') or state.startswith('3F') or state == '3D000'):
        category = 'sql_or_schema'
        explanation = 'PostgreSQL rejected SQL or a referenced database/schema/object. Use the SQLSTATE and stage to inspect migration/audit SQL and schema compatibility; do not reset tables.'
    elif (state and state.startswith('28')) or any(x in hints for x in ('password authentication failed', 'authentication failed', 'invalid password', 'tenant or user not found', 'sasl authentication')):
        category = 'authentication'
        explanation = 'Database authentication failed. Check the project database password, percent-encoding and exact Session pooler username/project reference.'
    elif any(isinstance(item, ssl.SSLError) for item in chain) or any(x in hints for x in ('certificate verify failed', 'ssl error', 'ssl connection', 'tls handshake', 'root certificate', 'sslmode', 'ssl is not enabled', 'server does not support ssl', 'ssl syscall')):
        category = 'tls'
        explanation = 'TLS negotiation or certificate validation failed. Keep TLS enabled; check the pooler endpoint, sslmode and CA configuration.'
    elif any(isinstance(item, socket.gaierror) for item in chain) or any(x in hints for x in ('could not translate host name', 'name or service not known', 'getaddrinfo failed', 'nodename nor servname', 'temporary failure in name resolution', 'failed to resolve host')):
        category = 'dns'
        explanation = 'Database hostname resolution failed. Check the exact Session pooler hostname and Render DNS/network access.'
    elif any(isinstance(item, TimeoutError) or type(item).__name__ in {'TimeoutError', 'ConnectionTimeout'} for item in chain) or any(x in hints for x in ('timeout expired', 'connection timed out', 'connection timeout', 'pool timeout')):
        category = 'timeout'
        explanation = 'Database connection or pool checkout timed out. Check network reachability, project availability and pool capacity.'
    elif 'permission denied' in hints or 'insufficient privilege' in hints:
        category = 'insufficient_privileges'
        explanation = 'The database role lacks permissions. Check private-schema ownership and migration/audit privileges without weakening RLS.'
    elif state == '53300':
        category = 'connection_capacity'
        explanation = 'The server connection limit was reached. Check Session pooler limits and the number of application workers/connections.'
    elif state == '57014' or state == '55P03':
        category = 'query_or_lock_timeout'
        explanation = 'A database operation was cancelled or could not obtain a lock. Inspect timeout/lock settings and other writers before retrying.'
    elif (state and (state.startswith('08') or state == '57P03')) or any(isinstance(item, (ConnectionError, OSError)) for item in chain) or any(x in hints for x in ('connection refused', 'network is unreachable', 'server closed the connection', 'connection reset', 'no route to host')):
        category = 'network_or_availability'
        explanation = 'The database connection is unavailable or was interrupted. Check the project status, Session pooler host/port and network reachability.'
    elif state and state.startswith('23'):
        category = 'constraint'
        explanation = 'A database constraint rejected the operation. Existing records were not reset; review schema/data compatibility.'
    elif any(isinstance(item, (ImportError, ModuleNotFoundError)) for item in chain):
        category = 'driver_dependency'
        explanation = 'A required database/application dependency could not be imported. Install the backend requirements, including psycopg[binary].'
    else:
        category = 'unclassified'
        explanation = 'Database operation failed without a recognized safe category. Use the stage, exception class and SQLSTATE; do not share raw errors or credentials.'
    return {
        'event': 'database_operation_failed',
        'stage': stage if stage in {'connection', 'migration', 'security_verification'} else 'connection',
        'exception_class': _class_name(original),
        'driver_exception_class': _class_name(chain[-1]),
        'sqlstate': state,
        'category': category,
        'explanation': explanation,
        **({'policy_code': policy.code} if policy else {}),
    }


def diagnostic_json(error, fallback_stage='connection'):
    return json.dumps(diagnostic(error, fallback_stage), sort_keys=True)
