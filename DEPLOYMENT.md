# Supabase PostgreSQL + Render + Vercel setup

No deployment, push, production connection or edit to a real `.env` was performed. These instructions supersede the earlier Neon/default-schema deployment notes.

## Frontend configuration follow-up (19 October 2026; not deployed)

### Diagnosed localhost connection failure

The user confirmed the browser origin is **http://localhost:5173**. Vite's `loadEnv` resolves both development and production VITE_API_URL to `https://smartspend-backend-lsk5.onrender.com` in the current workspace; the process variable is unset. The frontend therefore targets Render, not the local FastAPI server. The real `.env` was inspected only for that public URL and was not edited.

Read-only live probes with `Origin: http://localhost:5173` returned **401** for unauthenticated `GET /auth/me` in 1.70 seconds, with `Access-Control-Allow-Credentials: true` but **no Access-Control-Allow-Origin**. Its Content-Type preflight returned **400** with no allowed origin. The backend is reachable; the expected unauthenticated response is being withheld from this browser origin by CORS. Removing Content-Type on bodyless GET avoids an unnecessary preflight, but does not fix the missing origin grant. No evidence of cookie blocking was observed and no cookie-setting change is recommended as the fix for this incident.

In the **existing Render service → Environment**, edit the existing CORS_ORIGINS value by appending this exact text (unless already present):

```text
,http://localhost:5173
```

The backend expects a single **comma-separated string**, without JSON brackets, extra quotes, a wildcard or trailing slash. The complete value should have this form; replace the first part with the actual existing value, preserving all its origins:

```text
CORS_ORIGINS=EXISTING_COMMA_SEPARATED_ORIGINS,http://localhost:5173
```

Do not literally paste EXISTING_COMMA_SEPARATED_ORIGINS. The live dashboard's current value is not accessible here, so an exact complete replacement cannot safely be invented. Keep `APP_ENV=production`, `COOKIE_SECURE=true`, `COOKIE_SAMESITE=none`, the current DATABASE_URL and other secrets unchanged. Apply/restart the existing backend under your release process; no dashboard change, restart or deployment was performed by this work. Then retry the login alert. A successful unauthenticated probe should return 401 **with** `Access-Control-Allow-Origin: http://localhost:5173` and credentials true; the login POST preflight should return 200. No frontend restart is needed for a Render-only environment change. Vite must restart if its local .env is changed.

If you choose local development instead, use the isolated database setup in MANUAL_BROWSER_CHECKLIST.md and set the frontend process's VITE_API_URL to that local backend. For the current browser URL, set that isolated backend's process `CORS_ORIGINS=http://localhost:5173`, `APP_ENV=development`, `COOKIE_SECURE=false`, `COOKIE_SAMESITE=lax`. Restart both the local backend and Vite after changing process variables. Never start the local backend without explicitly overriding DATABASE_URL to the disposable database; the real backend .env may point at production. These development cookie settings must not be applied to Render. This pass keeps the existing frontend pointing at Render and does not silently switch databases or servers.

The frontend continues to use **VITE_API_URL**. For the existing Vercel project set:

```text
VITE_API_URL=https://smartspend-backend-lsk5.onrender.com
```

Use Root Directory `smartspend frontend`, build `npm run build`, and output directory `dist`. Vite embeds this public origin at build time. Production without an override defaults to the same HTTPS Render origin; only Vite development defaults to localhost. `.env.example` contains no credentials. Do not copy backend `.env` into Vercel or add DATABASE_URL/GEMINI_API_KEY to any VITE variable. No dashboard settings or deployments were changed in this pass.

For direct Vercel-to-Render cookie requests, the existing Render backend must have `APP_ENV=production`, `COOKIE_SECURE=true`, `COOKIE_SAMESITE=none`, and `CORS_ORIGINS=https://YOUR_ACTUAL_VERCEL_PRODUCTION_HOST`. Replace the placeholder with the precise deployed origin, without a path or trailing slash. Add individual trusted preview origins only when needed; do not use a wildcard origin. Existing middleware checks Origin on writes, and CORSMiddleware already allows credentialed GET/POST/PATCH/DELETE/OPTIONS requests. No backend source change is required for this configuration. The actual Vercel hostname and live dashboard settings were not provided/verified.

Browsers may still block third-party cookies even with correct CORS and SameSite=None; test the actual frontend/API domains before release. SameSite=None requires Secure. See [MDN CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS) and [Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie). If blocked, use same-site custom frontend/API domains, or deliberately configure a same-origin proxy that preserves cookies and the frontend Origin; use `COOKIE_SAMESITE=lax` only once the resulting request is same-site. A proxy also needs its `/api` prefix stripped before reaching FastAPI. No rewrite or custom domain has been installed automatically.

Before release, use MANUAL_BROWSER_CHECKLIST.md against an isolated backend, then check deployed Set-Cookie/CORS behavior with disposable release-test accounts under an explicit safe test workflow. Automated local tests manually maintain cookie jars; they do not emulate browser CORS, cookie privacy rules, microphone hardware or viewports. Keep the existing PostgreSQL TLS/RLS/migration setup below unchanged. Nothing here transfers SQLite records or changes database hosting.

## Target architecture

### Email authentication transition: schema 5 (not deployed)

New signup accepts `name`, `email`, `password`, and optional `monthly_income` (zero by default). Login accepts email/password. Names need not be unique. No environment-variable, CORS, cookie or API URL change is required.

Email policy: trim outer whitespace, validate syntax without DNS/deliverability checks, normalize international domains to ASCII, and lowercase the entire address. Non-ASCII local parts are unsupported. Dots and plus tags are preserved. Database canonical-value checks plus unique email enforce case-insensitive uniqueness even during concurrent requests. Format acceptance is **not ownership verification**: `email_verified` remains false. This release provides no email verification, recovery, email-changing or account-merging feature. Never treat matching emails/names as proof of ledger ownership.

The additive migration creates `email_accounts` linked by user ID, with a canonical-email check, unique email and password hash. Existing users, legacy credentials, sessions and all financial/chat records remain in place. It never infers emails from usernames. New users have email credentials only. SQLite retains its online backup and transactional version update; PostgreSQL retains the advisory lock, private schema, transactional DDL, RLS and final security audit. The optional SQLite transfer includes this table after upgrading only its temporary copy.

Exact release sequence (operator actions; none performed on production here):

1. Rehearse on a disposable PostgreSQL project first. Supply `SMARTSPEND_TEST_POSTGRES_URL` and `SMARTSPEND_TEST_POSTGRES_CONFIRM=disposable-smartspend-database`, then run `python -m unittest -v test_postgres_integration`. No isolated PostgreSQL target was available here, so live PostgreSQL upgrades and constraints remain unverified.
2. Arrange a brief signup maintenance window. Old frontend username registrations are incompatible with the new contract. Take a provider snapshot/secure export and retain the matching prior code/settings. Preserve the working environment, CORS and cookie configuration.
3. From `smartspend backend`, run `pip install -r requirements.txt`. For an existing PostgreSQL schema version 2/3/4, only after taking the backup temporarily set `POSTGRES_BACKUP_CONFIRMED=true`; run `python manage_database.py migrate`, then `python manage_database.py verify`; remove the attestation afterward. This implementation did not set the flag. Fresh initialization needs no upgrade attestation. SQLite migrates through migrations.migrate at application startup and creates its own online backup before upgrading a populated file; manage_database.py deliberately refuses SQLite. Never run local tests on the real ledger.
4. Release the matching backend before the frontend during that window. Preserve the Render start command below (`main:app`). The old `/auth/login` username body and dedicated `/auth/legacy-login` remain supported only for accounts without enrolled emails. Existing cookies remain valid. Then release the matching frontend with its existing API URL; a new frontend against the old backend will not work.
5. Existing users choose **Sign in to an older account**, then **Account → Add your sign-in email**. Enrollment requires an active session and the current password, preserves user ID/records/sessions, and immediately disables username login for that account. Duplicate-email enrollment fails without merging anything. Accounts without existing passwords still require the existing externally verified operator enrollment process. Retire the temporary legacy endpoint only in a separately planned release after users transition.
6. Verify fresh signup, email login, session restoration, legacy enrollment, persistence and two-account isolation before reopening signup.

Backend-only release preparation: all frontend changes remain uncommitted and are not included in this backend commit. The checked-in frontend at the pre-update origin/main uses POST /users onboarding and a local user ID, without credentialed auth; it is incompatible with the secured backend. The actual Vercel revision was not inspected, so live frontend compatibility is not certified. A deployed username-auth frontend can still restore existing cookies and log in unenrolled legacy users, but username signup fails validation (422). Once enrolled, an account needs the matching email-capable frontend to sign in. Do not enroll users, reopen signup or call the transition complete until that frontend is separately approved and released.

PostgreSQL backup requirements: the migration does not create a backup. Before upgrading an existing version 2/3/4 schema, stop application writers, take a restorable provider snapshot or protected pg_dump export containing the application schema/data and retain the matching old code and service settings. Confirm the export completed and rehearse restoration in isolation. Keep it outside Git. The attestation is required only while crossing to version 5; fresh initialization and repeat runs at version 5 do not require it. Do not use manage_database.py verify from the new revision as a pre-upgrade check of version 4: it intentionally expects version 5.

Render operator procedure (future manual actions, not executed here): confirm the existing service is connected to this repository/main and disable dashboard automatic deploys before any release. Keep Oregon, root directory smartspend backend, build pip install -r requirements.txt, and the existing secrets/CORS/cookie values. After the backup, an operator with an appropriate protected environment can install this revision's requirements and run python manage_database.py migrate followed by python manage_database.py verify, supplying the backup attestation only to the upgrade process and removing it immediately. If an external operator environment is unavailable, the existing Render startup migration can do the upgrade: only after the backup, the operator supplies the temporary attestation, manually deploys this specific backend commit, checks migration/verification/startup logs, then removes the attestation. Removing a dashboard variable may restart/redeploy the service; rerunning schema-5 migration is safe. Leave the permanent start command as python manage_database.py migrate && python manage_database.py verify && uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1 --no-proxy-headers. Confirm the read-only health endpoint and sanitized schema-5 verification before coordinating the separate frontend release. Do not create production test accounts or mutate real financial records as part of release preparation. A failed security audit must stop startup, never be bypassed.

Rollback requires stopped writers, a matching code/schema backup, and reconciliation of post-cutover writes. Old code rejects schema 5 and cannot authenticate email-only users. Do not lower version markers, remove email rows or discard new accounts to force rollback. Keep both databases/backups; the rollback precautions below also apply.

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

`migrate` takes a PostgreSQL advisory transaction lock, creates only the private application schema/tables, records schema version 5, applies deny-by-default RLS/security and audits the result before commit. It is repeatable and does not drop application tables or delete records. An unexpected/unversioned populated smartspend schema is refused. Existing Supabase public/managed tables do not block creation of this separate schema and are never moved or changed.

For an older recognized private schema (version 2, 3 or 4), first take a provider snapshot or pg_dump export. Only after that set POSTGRES_BACKUP_CONFIRMED=true for the upgrade and remove it afterward. The flag is an operator attestation, not an automatic backup. Fresh empty-schema initialization needs no pre-existing-data backup. No table rebuild/conversion is attempted on unrelated PostgreSQL data. Tables left in `public` by an earlier app version are not automatically moved; review and plan that separately before pointing the backend at a new empty schema.

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


## Sanitized startup diagnostics

Database command failures write one structured JSON diagnostic to stderr and exit nonzero. Fields identify `stage` (`connection`, `migration`, or `security_verification`), outer/driver exception class, validated PostgreSQL `sqlstate` when present, a fixed category and a fixed explanation. Missing SQLSTATE is emitted as null; it is not invented. Configuration/driver import failures are also sanitized. No raw exception message, connection URL, password, SQL, SQL parameter or financial record is printed. Fixed policy codes identify RLS/privilege/version refusals without bypassing them.

Typical categories: `authentication` (28P01/28000), `dns`, `timeout`, `network_or_availability`, `tls`, `insufficient_privileges` (42501), `sql_or_schema` (for example 42601/42P01/42883), and `security_audit` (the app's explicit policy checks). The error stage remains security_verification if the migration's final audit fails; the transaction still rolls back. Use these safe fields to diagnose the issue; do not paste raw Render environment values or unsanitized driver errors.

The Render dashboard start command must use **main:app**, not `uvicorn main`:

```text
python manage_database.py migrate && python manage_database.py verify && uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1 --no-proxy-headers
```

The checked-in render.yaml already uses main:app. A Git push does not itself prove an existing dashboard command was updated. This diagnostics change does not disable TLS, remove the audit, reset tables or establish that the live Supabase connection has passed.


## Empty schema-4 deployment exception (local change; not pushed)

Latest operator evidence: the user ran the production read-only SQL audit and reported schema version 4, all 10 application data tables at exactly zero rows, and one smartspend_schema metadata row. This establishes operator-reported emptiness at audit time; it is not an agent-run PostgreSQL migration/locking test. The transactional locked recheck remains mandatory. The earlier inability to connect from this workspace is historical, not a rejection of the supplied audit results.

This section supersedes the unconditional schema-4 backup-attestation requirement above. Schema 2/3 upgrades still require a real backup and attestation. Schema 4 may upgrade without the flag only when the migration itself recognizes the complete previous table set, locks all application tables and the marker in SHARE ROW EXCLUSIVE mode, re-reads version 4, proves the executing role has unfiltered visibility, and finds every application data table empty. Locks last through migration/security audit/commit; READ COMMITTED is explicitly selected before queries, so preceding committed writers cannot hide behind a stale snapshot. Lock acquisition times out after 10 seconds. Any rows, partial/unexpected table set, hidden-row risk or changed marker refuse the exemption; lock/query errors abort. No tables/schemas are dropped. RLS/security audit still run before commit. No backup is claimed or flag set by this path.

The local protected backend configuration selects SQLite. The agent has not connected to production PostgreSQL. Production emptiness was subsequently confirmed by the operator-reported SQL results above, rather than an agent-run database query. A previous read-only observation alone would not authorize the exception: the migration rechecks under locks. Do not alter the local .env to guess the production URI or use a reset script. An operator may perform the read-only observation in the existing production Supabase SQL editor without sharing credentials. All application relations must be included (users, credentials, auth_sessions, budgets, transactions, bills, bill_payments, chat_messages, expense_proposals, import_batches, plus email_accounts if already present); marker rows are version metadata, not user data. Only an owner/non-forced-RLS or BYPASSRLS/superuser role can certify emptiness. Unknown or inaccessible relations mean unverified.

Exact future release sequence:

1. Verify production emptiness read-only through an already authorized PostgreSQL connection/dashboard, confirming the smartspend schema version and every application relation. Arrange signup maintenance and stop application writers. Preserve existing DATABASE_URL/CORS/cookies/root/build/start settings. Do not set POSTGRES_BACKUP_CONFIRMED unless an actual restorable backup exists.
2. Review/commit/push the local empty-schema exception separately when authorized. Commit 877031e4bcc81c1d3553519dfacfcf463f906a75 alone does NOT contain it. Render Auto-Deploy is Off per the user's dashboard confirmation.
3. Render root stays smartspend backend; build stays pip install -r requirements.txt. Manually deploy the reviewed new backend revision when authorized. Start stays python manage_database.py migrate && python manage_database.py verify && uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1 --no-proxy-headers. For a qualifying empty schema 4, leave the backup flag unset. Alternatively run python manage_database.py migrate then python manage_database.py verify from that revision in a protected operator environment before starting it. Never bypass a backup/security refusal.
4. Confirm migration reports schema 5, the security audit passes and the health endpoint succeeds. Keep signup unavailable until the separately reviewed email-capable frontend is released. Backend first, frontend second; preserve VITE_API_URL. Existing username signup is incompatible.
5. Test signup/email login/logout-login persistence and synthetic legacy enrollment against an isolated/explicitly approved release-test environment. Production financial records must not be used as test fixtures. Re-enable signup only after compatibility checks pass.
6. If any user data is found, stop: take/validate the backup before the normal attested upgrade. After new records exist, rollback requires matching code/database backup and reconciliation. Even for an empty schema, old code cannot be redeployed against schema 5: keep the new backend or plan a reviewed restoration rather than lowering the marker, dropping objects or resetting schemas.

The operator confirmed production emptiness using live SQL. The new PostgreSQL migration and lock-race behavior remain unverified on a live database; mocked tests do not establish those results.
