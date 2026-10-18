# Supabase PostgreSQL + Render + Vercel setup

No deployment, push, production connection or edit to a real `.env` was performed. These instructions supersede the earlier Neon/default-schema deployment notes.

## Target architecture

React on Vercel calls FastAPI on Render (Oregon). FastAPI keeps its current password/session authentication and ownership checks. Supabase in West US (Oregon) supplies PostgreSQL only: no Supabase Auth, frontend database client, anon key or service_role API key is used.

The application owns only the **smartspend** PostgreSQL schema. It does not create/drop/alter tables in `public`, `auth`, `storage`, or other Supabase-managed schemas. Keep automatic table exposure disabled and do not add smartspend to the Data API exposed-schema list. Automatic RLS is retained, but the migration explicitly enables RLS and revokes API-role privileges rather than relying on dashboard defaults.

Official references: [Supabase connections](https://supabase.com/docs/guides/database/connecting-to-postgres), [SQLAlchemy guidance](https://supabase.com/docs/guides/troubleshooting/using-sqlalchemy-with-supabase-FUqebT), [RLS](https://supabase.com/docs/guides/database/postgres/row-level-security), [secure data](https://supabase.com/docs/guides/database/secure-data).

## 1. Build the server-only URI safely

In Supabase Connect select **Session pooler**, **URI**. Copy the exact username (usually postgres.PROJECT_REF), pooler host, database and **port 5432** displayed for your project. Do not guess the host index/region or use transaction mode on 6543. Session mode provides IPv4 connectivity suitable for Render.

The SQLAlchemy driver is **psycopg 3**, installed by `psycopg[binary]>=3.2,<4`. Use:

```text
postgresql+psycopg://postgres.PROJECT_REF:ENCODED_DATABASE_PASSWORD@EXACT_SESSION_POOLER_HOST:5432/postgres?sslmode=require
```

`postgresql://` and `postgres://` inputs are normalized to psycopg 3, but the explicit scheme above avoids selecting the wrong driver. `postgresql+psycopg2://` is deliberately rejected. The password is the **project database password**, not your Supabase login password, anon key or service_role key.

Percent-encode the password component exactly once. For example, the fictitious password `demo@:/#?%` becomes `demo%40%3A%2F%23%3F%25`. Other common replacements: `&` -> `%26`, `+` -> `%2B`, space -> `%20`. Do not encode the entire URI or double-encode an already encoded password. Square-bracket placeholders must be replaced, not retained. Use a local password manager/editor or Python `urllib.parse.quote(password, safe='')`; never print the actual password/encoded password/complete URI, put them in command-line arguments, send them to chat, commit them or use an online encoder. Programmatic callers can also construct a SQLAlchemy URL object with `URL.create(..., password=raw_password)` without printing it.

Store the completed URI only as the backend's secret **DATABASE_URL**. Do not store it in a frontend VITE variable. For local operator commands, populate the current process's environment through your protected secret tooling; do not overwrite an unrelated `.env`. Keep SQL logging disabled. CLI failures suppress raw driver errors/parameters. `sslmode=require` enforces encryption; `verify-full` with Supabase's CA certificate is a stronger option when configured correctly.

The engine has pool_size=3, max_overflow=2 (at most five DB connections per worker), pool_timeout=10 seconds, connect_timeout=15 seconds, pool_recycle=300 seconds and pre-ping on checkout. Prepared statements are disabled for pooler compatibility. Keep one Render worker unless you budget shared pooler capacity and introduce a shared rate limiter.

## 2. Explicit repeatable migration and security verification

With the PostgreSQL DATABASE_URL securely populated in the operator environment, from `smartspend backend`:

```text
python -m pip install -r requirements.txt
python manage_database.py migrate
python manage_database.py verify
```

Use `./venv/Scripts/python.exe` instead of `python` when using the existing Windows virtual environment. Set `COOKIE_SECURE=true` as well if APP_ENV=production; the auth module checks it even for operator commands.

`migrate` takes a PostgreSQL advisory transaction lock, creates only the private application schema/tables, records schema version 4, applies deny-by-default RLS/security and audits the result before commit. It is repeatable and does not drop application tables or delete records. An unexpected/unversioned populated smartspend schema is refused. Existing Supabase public/managed tables do not block creation of this separate schema and are never moved or changed.

For an older recognized private schema (version 2 or 3), first take a provider snapshot or pg_dump export. Only after that set POSTGRES_BACKUP_CONFIRMED=true for the upgrade and remove it afterward. The flag is an operator attestation, not an automatic backup. Fresh empty-schema initialization needs no pre-existing-data backup. No table rebuild/conversion is attempted on unrelated PostgreSQL data. Tables left in `public` by an earlier app version are not automatically moved; review and plan that separately before pointing the backend at a new empty schema.

`verify` is read-only and prints a sanitized summary (schema/version/table count, API-role names and security status), never credentials or rows. It checks every expected table, RLS enabled, no unexpected policies, effective schema/table/column/sequence privileges of anon/authenticated/service_role, PUBLIC schema/object grants, and the backend role's ability to access the deny-by-default tables. A failed audit prevents startup. It does not certify dashboard Data API exposure settings or arbitrary user-created SECURITY DEFINER functions elsewhere; review those separately.

The default postgres project role owns the application tables and can bypass RLS as their owner. That credential is powerful and belongs only on the server. **RLS does not enforce FastAPI users' ownership**: those sessions are not Supabase JWTs and do not set auth.uid(). FastAPI continues authenticating sessions and filtering/checking user_id for every resource. No permissive public policy or fake auth.uid integration is added. A future restricted runtime role needs deliberately designed grants/RLS policies; do not substitute anon/authenticated as the backend DB role.

The application import/startup performs only the PostgreSQL version/security audit, not CREATE/DROP/ALTER. The prepared Render start command explicitly runs the repeatable migration first so a new database can initialize without a paid pre-deploy hook.

## 3. Exact Render settings (do not deploy yet)

Review/update the existing backend service, not a second accidental service:

- Region: Oregon; Root Directory: `smartspend backend`; Python runtime.
- Build command: `pip install -r requirements.txt`
- Start command:

```text
python manage_database.py migrate && python manage_database.py verify && uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1 --no-proxy-headers
```

- Secret DATABASE_URL: your completed Session pooler URI with psycopg scheme, port 5432 and TLS.
- APP_ENV=production
- CORS_ORIGINS=https://YOUR_ACTUAL_VERCEL_PRODUCTION_HOST (exact origin, no path/trailing slash/wildcard; comma-separate only explicitly trusted additional origins).
- COOKIE_SECURE=true
- COOKIE_SAMESITE=none for direct cross-site Vercel -> Render requests.
- Optional existing GEMINI_API_KEY remains a server secret; it is unrelated to database access.
- Automatic deployments remain disabled in render.yaml. No persistent Render disk is required when all application records use Supabase.

Set only the frontend build variable VITE_API_URL=https://YOUR_ACTUAL_RENDER_API_HOST on Vercel. The URI/password/API DB keys never belong there. Cross-site HttpOnly cookies can still be blocked by browser privacy settings. Prefer same-site custom frontend/API domains or a same-origin Vercel `/api` rewrite to Render that strips `/api`; use COOKIE_SAMESITE=lax for that arrangement. Verify Set-Cookie/login/logout in real browsers using the actual hostnames before release. Database preparation alone does not solve third-party-cookie restrictions.

## 4. Optional transfer of the existing SQLite ledger

**Changing DATABASE_URL does not transfer records.** The existing SQLite file stays untouched. If you want those records in Supabase:

1. Stop all writers. Keep your own secure source backup. Initialize/verify the empty private PostgreSQL schema using the commands above.
2. In an operator environment with the Supabase URL securely set, run:

```text
python transfer_to_postgres.py /absolute/path/to/smartspend.db
```

3. The tool opens the original read-only, makes a timestamped SQLite backup, upgrades only a temporary working copy and verifies target security. It locks the application target tables and refuses a nonempty target. It copies records in foreign-key order, validates row counts and every persisted column (including integer cents, ownership IDs, password hashes, sessions, bill links and chat), resets ID sequences and commits inserts together. Differences abort the transfer. SQL/credentials/financial rows are not printed. Progress counts are labeled commit-pending until success.
4. It retains all original files/backups. Inspect final counts, known totals, login and chat before changing Render's connection. Legacy users without credentials still require externally verified enrollment; a new signup does not claim an old ledger.
5. A live SQLite-to-Supabase transfer has **not** been performed or verified here. If a transfer fails, do not drop/reset tables to retry: inspect the safe error and target state. PostgreSQL sequence increments are not transactional, but an empty-target retry resets sequences; no financial rows are overwritten.

## 5. Tests and actual evidence

No isolated PostgreSQL URL, local PostgreSQL tooling or live Supabase test database was supplied. No production connection was attempted. SQLite tests and mocked PostgreSQL configuration/DDL checks are not live PostgreSQL evidence.

Run the default local suite (a shared fixture isolates DATABASE_URL and disables paid AI before app imports):

```text
python -m unittest discover -s . -p "test_*.py" -v
```

For **real PostgreSQL tests**, use a different disposable database/project only. Securely set SMARTSPEND_TEST_POSTGRES_URL, set SMARTSPEND_TEST_POSTGRES_CONFIRM=disposable-smartspend-database, install requirements, then run:

```text
python -m unittest -v test_postgres_integration
```

The test refuses the configured application's host/port/database, runs real private-schema migration/security/persistence checks, and tests SELECT/INSERT/UPDATE/DELETE denial with actual anon/authenticated roles. Those roles must already exist (a disposable Supabase project supplies them). It creates isolated test rows and intentionally does not drop tables or clean data. It is skipped unless both explicit test settings are supplied. Never supply the production Session pooler URI as the test URI.

Local browser/voice checks remain in MANUAL_BROWSER_CHECKLIST.md. Live RLS/ACL verification must be completed by running `manage_database.py verify` against the intended target before deployment; it has not passed on Supabase merely because offline tests passed.

## 6. Rollback without data loss

Before a live migration/transfer, back up the source and any existing target. Keep the prior Render settings and matching code revision privately. Keep deployment disabled until verification is complete.

- If preparation fails, no deployment changed. Keep the SQLite source and do not delete either database.
- If target migration fails, PostgreSQL DDL/security/version changes roll back together. Correct permissions/configuration and repeat the migration; do not reset Supabase-managed schemas.
- If transfer fails, target row inserts roll back; source and backup remain. Re-audit the target before retrying.
- After a later cutover, stop writers before rollback. Repointing to an old SQLite file would hide all new Supabase transactions/chat/accounts written after cutover. Export/reconcile those writes first; do not silently abandon them. A Render free-service SQLite file is not a durable rollback destination: use a real persistent disk or a backed-up PostgreSQL database.
- Match the schema/code/money format when restoring. Never lower a version marker, divide cents manually, drop financial tables or restore over Supabase-managed schemas.
