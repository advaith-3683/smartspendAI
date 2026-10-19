# SmartSpend completion report

Updated 18 October 2026 after the account-persistence clarification and responsive-dashboard requirements. This report supersedes the earlier Phase 1-3 report. This report describes the complete local workspace. The backend-only commit scope includes backend source/tests, ignore rules and deployment documentation; frontend implementation changes remain outside that commit. No deployment is claimed.

## Account persistence and security

Accounts, credentials, sessions, transactions, budgets, bills/payment links, Coco chat, expense proposals and import retry keys are stored in the backend SQL database and linked to their owner. Browser localStorage is not the database. A legacy localStorage user ID is removed and never grants access.

Signup creates a separate account with a salted scrypt password hash. Login issues an opaque HttpOnly cookie, stores only a token hash server-side and restores the authenticated owner. Sessions expire after 24 hours. Production authentication requires secure cookies. Logout revokes only the session; it never deletes financial records, accounts, proposals or stored chat. Another browser can log in with the same credentials and continue the same ledger.

Every financial route is session protected. User IDs supplied for compatibility must match the session, creation handlers derive identity from the authenticated user, and resource IDs receive ownership checks. Authenticated transaction editing and proposal resolution are also owner scoped. The destructive database-reset endpoint is removed. Exact CORS origins, mutation-origin checks, rate limits, size limits and bounded AI/history inputs remain in place.

Legacy ledger records are retained without a public claim-by-ID/name/email flow. `enroll_legacy.py` provides operator-controlled credential enrollment after external ownership verification. No simulated email verification or password reset was added.

## Persistent storage and deployment preparation

The original repository had a relative SQLite path and no deployment/persistent-disk manifest. No connected deployment account or actual mounted disk was available to certify. The existing financial database and `.env` were not modified by this work.

Implemented:

- A stable default SQLite path beside `database.py`, independent of the working directory when DATABASE_URL is omitted.
- PostgreSQL/psycopg support with small pools, pre-ping, TLS requirement in production and connection timeouts.
- Portable date queries and SQLite write-lock/PostgreSQL row-lock handling for bill actions.
- BIGINT minor-unit money storage for fresh schemas and Decimal arithmetic.
- Version 4 additive schema initialization/migration, serialized and atomic SQLite startup/conversion/DDL/version updates, automatic pre-migration SQLite backups and refusal to guess an unversioned populated PostgreSQL database. An older hosted schema requires an operator backup acknowledgement before upgrade.
- Production SQLite startup refusal unless an absolute database path lies in an explicitly configured existing persistent directory. This is a configuration guard, not proof a hosting provider preserves that directory.
- `transfer_to_postgres.py`: an offline operator tool that backs up the SQLite source, migrates a temporary copy, transfers rows into an empty PostgreSQL database in a transaction and resets sequences. It preserves source data and refuses merges/overwrites.
- A prepared backend `render.yaml` with external DATABASE_URL, production settings, one worker and autoDeploy disabled.
- `.env.example` and `DEPLOYMENT.md` with Neon Free setup, TLS/cookie/origin instructions, transfer/backup steps and the persistent-disk alternative.

Official Render documentation confirms free web-service filesystems are ephemeral and persistent disks require paid services. Official Neon documentation was checked for a suitable free persistent PostgreSQL option. Creating the provider account/project and supplying the secret connection string remain user setup steps; no hosted database or deployment was provisioned.

## Responsive UI/UX redesign

Applied the requested dark theme with muted mint accents, readable typography, consistent surfaces/spacing, reduced glow, keyboard focus states and reduced-motion support. Added desktop sidebar navigation and compact horizontally scrollable mobile navigation.

- **Overview:** income, actual incurred spending, remaining income, clearly qualified projection, actual category breakdown including unbudgeted expenses, current overdue/next-seven-day bill reminders and quick actions.
- **Transactions:** selected-month search/category/frequency filters, add/edit/delete controls, decimal amounts, accessible inline editing, SMS/CSV/PDF preview and reviewed import.
- **Budgets & Bills:** explicit category budgets, existing pace/progress cards and paid/unpaid recurring-bill actions with success feedback. Linked bill payments cannot be edited as ordinary expenses.
- **Goals & Insights:** savings planner, subscription detection, selected-period anomalies and weekly digest.
- **Coco:** account-backed persistent history, voice controls and persisted pending expense proposals with explicit Save/Cancel. Leaving Coco stops voice capture/output; logout unmounts it.
- **Account:** profile/income editing, save feedback and logout on both desktop and mobile.

Added loading/empty/error states, retry controls, success notices, submit guards and stale-response protection. JSON and multipart requests share authentication/error handling and a 60-second timeout; ambiguous save timeouts instruct the user to check the ledger before retrying. Main month changes clear old period data, request revisions prevent old responses overwriting newer selections, and captured mutation callbacks cannot repopulate the wrong period. Forms and bill panels reset safely when the selected period changes. React render smoke checks catch runtime references that a production bundle alone cannot catch.

## Coco expense review

Coco's tool no longer inserts financial spending directly. It validates and stores an owner-linked proposal, tells the user it awaits review and returns Save/Cancel controls. Pending proposals survive logout, a browser change and refresh. Save creates the expense atomically; repeated Save returns the original result without another transaction. Cancel records no expense. Another user cannot view or resolve the proposal. Failed AI responses roll back draft writes. Existing saved conversation history is retained; retrieval/context are bounded.

## Imports and financial fixes retained/completed

- Debit/withdrawal columns outrank generic amounts; credit/deposit/balance columns are excluded. Signed and explicit transaction-type formats are supported when direction is clear. Ambiguous unsigned rows are skipped.
- Previews allow selecting rows and editing date, merchant, category and amount. Invalid explicit dates are skipped. Undated SMS defaults to today. Local keyword categorization avoids per-row paid AI calls.
- Import commits are atomic and use a stable batch retry key from the UI, preventing duplicate insertion after a lost response/retry. Independently reparsing the same statement creates a new batch; historical duplicate matching is not automatic.
- Positive/finite/bounded/two-decimal money and bounded dates/text/batches/sources/frequencies are validated server-side. Income can be zero. HALF_UP migration and Decimal sums avoid binary-float arithmetic for financial calculations.
- Categories are preserved without invented budgets; total incurred spending includes unbudgeted categories and excludes future transactions. Purchase checks use the selected month/year and explicitly distinguish missing budgets.
- Projections extrapolate daily spending only; monthly/one-time entries count once. Actual overspending and projected risk differ, and alert text uses backend projections. Historical/future months have sensible incurred behavior.
- Bills use atomic retry-safe payment changes, correct prior-month overdue states, month-length clamping and reminders across month boundaries. Reads/payments do not create or overwrite budgets. Deleting a payment clears its status; deleting a recurring template retains historical expenses.
- Savings use one three-complete-month baseline window, exclude current/future entries, label sparse history and protect fixed costs/recurring-bill categories. Discretionary cuts cap at 60% and unsupported goals are reported.
- Weekly totals explicitly exclude monthly recurring expenses. Zero prior-week spend shows N/A rather than a false 0% change. Anomalies align with the selected month or are explicitly current.
- Gemini limits/timeouts and deterministic savings/digest fallbacks remain. Core tracking and persistence do not require paid AI.

## Verification actually performed

Backend regression command, from the repository root:

```powershell
& '.\smartspend backend\venv\Scripts\python.exe' -m unittest discover -s 'smartspend backend' -p test_regressions.py -v
```

**23 tests passed in the full regression suite, plus one additional targeted PDF test passed** against isolated temporary SQLite databases and an ephemeral local HTTP server. AI responses are mocked or deliberately unavailable; no paid requests were made. Coverage includes:

- Signup, profile editing, session restoration/expiry, copied-cookie revocation and protected-route coverage.
- Signup -> add transactions/budget/bill/chat -> logout -> login with a separate cookie jar -> retrieve the same records -> add another transaction.
- Cross-user read/write/delete denial, including transaction edits, bill actions, chat and proposal resolution.
- A fresh backend Python process using the same disk database: existing sessions/credentials/transactions remain usable and a new expense persists back to the original process. This checks persistence independent of in-memory application state; it is not an actual cloud redeploy test.
- Coco proposals create no spending until Save, survive another login, save once under retries and cancel without spending.
- Concurrent bill pay retries, repeat unpay, transaction deletion/status repair, preserved history, read purity, February clamping and cross-month reminders.
- Money/date/text/batch validation, exact 0.10 + 0.20 accounting, projections, purchase periods/missing budgets and category preservation.
- Fixed-cost/sparse-history savings behavior and weekly recurring-payment definitions.
- Credit-before-debit statement columns, signed/type formats, ambiguity handling and retry-safe imports.
- A real multipart upload over 5 MiB, AI timeout/output settings, unavailable-AI fallbacks and failed-chat rollback.
- SQLite backup contents, idempotence, concurrent startup and full rollback after an invalid legacy value; production storage guard; PostgreSQL BIGINT schema compilation.
- A separate generated table-PDF regression exercised actual pdfplumber extraction and verified debit import/credit exclusion. This is synthetic parser coverage, not representative bank-statement validation.

Frontend checks:

```powershell
npm.cmd run build
node test-render.cjs
node test-api.cjs
```

Production Vite build passed. Seven server-render smoke states passed: login plus all six workspace sections. Three frontend API checks also passed: authenticated JSON requests, expired upload-session logout, and readable validation errors. These are runtime/API checks, not browser interaction or viewport screenshot tests.

`git diff --check` passed. Enrollment/transfer tools passed Python syntax checks. PostgreSQL schema/query portability was prepared, but no live PostgreSQL connection, hosted transfer or provider snapshot was exercised.

## Remaining setup and verification

1. Follow DEPLOYMENT.md to create a Neon Free database or attach a real persistent SQLite disk. Store DATABASE_URL only in backend secrets. If existing data must move, stop writers and use/verify the transfer tool before changing the backend connection.
2. Keep exact CORS origins and HTTPS cookie configuration. Same-site hosting is preferred; cross-site third-party-cookie restrictions can prevent sessions. Verify this using the actual frontend/API hostnames.
3. Back up the database and externally enroll legacy owners as needed. Existing data has not been migrated or transferred by this session.
4. On the actual host, verify restart/redeploy persistence, cross-browser login, totals and chat before release. The prepared configuration has not been deployed and no live storage guarantee is claimed.
5. The browser tool inventory exposed no browser or native-app surfaces. Desktop/mobile screenshot inspection, keyboard interaction, real browser login/refresh and speech recognition/synthesis remain unverified. Responsive CSS and seven server renders do not replace that visual QA.
6. Live Gemini calls/function calling and representative/scanned/encrypted PDF statements remain unverified. The inherited google-generativeai SDK emits a deprecation warning and needs a separately tested successor-SDK migration.
7. In-process limits require one worker or a shared production limiter. Provider free-tier limits/backups need ongoing monitoring. Separate imports of the same bank file are not automatically deduplicated across different batches.

No deployment, push, production-record seeding, secret exposure or reset was performed. The project is ready for review and the documented hosting setup, not certified fully production-ready.


## Local browser verification requested before deployment

Rechecked browser availability on 18 October 2026. The computer/browser inventory returned `apps: []` and `browsers: []`. No local browser interaction, screenshot inspection, microphone permission or audio playback could be performed. This pass did not start a backend against the existing financial database, read or change the open Travel_app `.env`, modify SmartSpend secrets, deploy or push.

| Requested browser check | Actual result in this pass |
| --- | --- |
| Signup, transaction/budget/bill creation, logout and login | Not run in a browser; prior isolated HTTP coverage remains separate |
| Backend stop/restart and a separate browser context | Not run in a browser; prior fresh-process HTTP coverage remains separate |
| Second-account read/write isolation | Not run in a browser; prior isolated API tests remain separate |
| Desktop/mobile navigation, forms, month switching, imports and errors | Not run; production build/render/API checks do not establish browser UX correctness |
| Coco chat, explicit expense confirmation and voice | Not run in a browser; proposal API tests used mocked AI, not live Gemini; physical microphone/audio tests are manual |

A short executable setup and six-part manual checklist are in [MANUAL_BROWSER_CHECKLIST.md](MANUAL_BROWSER_CHECKLIST.md). The setup uses a new uniquely named temporary SQLite database, dedicated localhost ports and process-only settings; restarting reuses that same test file. It defaults to no Gemini calls and explains the additional key/quota requirement for successful live chat. No browser check is marked passed and no new test run is claimed in this documentation pass.

Deployment files were inspected again: `render.yaml` specifies a free backend service, no attached disk, production mode, secure SameSite=None cookies, one worker, and disabled automatic deployment. `DATABASE_URL` and `CORS_ORIGINS` are required external settings. This configuration requires a persistent **external PostgreSQL database**, not the default SQLite file. Create a dedicated Neon project/database (Free plan if suitable), store its TLS connection string as backend DATABASE_URL, and retain that same project/database across backend restarts and redeployments. No live hosted database connection or disk attachment has been verified.

If preserving existing SQLite records when moving to PostgreSQL, stop writers, keep a backup, transfer to a dedicated empty target using the documented operator tool, verify records/login, then change deployment settings. The transfer tool has not been exercised against live PostgreSQL. Never point the app at a fresh empty hosted database and assume existing local records were moved. SQLite is an alternative only after changing to a host/service with a real persistent disk, mounting it (for example at /var/data), setting an absolute DATABASE_URL inside that mount and PERSISTENT_DATA_DIR, and verifying the actual mount survives a redeploy. A directory or environment variable alone does not establish persistence. See [DEPLOYMENT.md](DEPLOYMENT.md) for exact settings and cookie/origin requirements.


## Supabase preparation ? 18 October 2026

This section supersedes earlier Neon/default-schema preparation. The requested target is Vercel -> Render Oregon -> Supabase West US/Oregon, Session pooler URI, automatic RLS enabled and automatic table exposure disabled. Supabase is PostgreSQL storage only; FastAPI auth/ownership/session handling remains.

Implemented:

- Explicit psycopg 3 URL/driver handling (`psycopg[binary]>=3.2,<4` already in requirements), normalized PostgreSQL aliases, rejection of psycopg2/transaction-pooler URIs and mandatory TLS for Supabase pooler connections. URI parsing errors omit the supplied value.
- Session-pooler settings: port 5432, pool_size=3, max_overflow=2, pool_timeout=10s, connect_timeout=15s, pool_recycle=300s, pre-ping and hidden SQL parameters. Prepared statements disabled. SQLite connection arguments remain only in their dialect branch.
- All PostgreSQL model tables are qualified in private `smartspend`, with internal foreign keys preserved. `public`, `auth`, `storage` and other managed schemas are untouched. SQLite PRAGMAs/migration/conversion paths remain isolated to local/legacy SQLite. Existing money remains BIGINT minor units/Decimal; app ownership checks and bill row locks are retained.
- `manage_database.py migrate` provides advisory-locked, transactional, repeatable private-schema creation/hardening. No table drops or financial-row resets. Unknown/unversioned private schemas are refused; known upgrades require backup acknowledgement. PostgreSQL app startup verifies instead of performing DDL.
- `manage_database.py verify` audits expected tables/version, RLS enabled, absence of unexpected policies, effective PUBLIC/API-role schema/table/column/sequence access and backend-owner/bypass capability. Migration revokes access for PUBLIC, anon, authenticated and service_role, and restricts future defaults inside the app schema only. Automatic RLS/table-exposure dashboard settings alone are not treated as proof of security. The backend owner's RLS bypass is explicitly documented; FastAPI per-user checks remain essential. No auth.uid policy or Supabase Auth substitution was added.
- Optional transfer now requires a separately initialized/verified empty target, maps SQLite reads to their original schema, locks target app tables, copies all accounts/credentials/sessions/financial/history data, resets qualified sequences and compares row counts/every persisted column before commit. Source opens read-only and only a backed-up temporary copy is migrated. Live transfer remains untested.
- Tests share one explicit temporary database fixture before importing app/database modules, preventing test discovery order from accidentally selecting a real configured database. AI credentials are disabled in the test process; no .env files are changed.
- `.env.example`, Render Oregon configuration and DEPLOYMENT.md now specify the exact session-pooler URI, secure password encoding, migration/build/start commands, private-schema RLS design, optional transfer validation, rollback and Vercel/Render cookie/origin requirements. Automatic deployment stays disabled.

Actual verification:

- **24 SQLite regression tests passed**, including account persistence/isolation, sessions, bills, money, proposals, imports, generated PDF, restart and migration rollback/concurrency. This is SQLite evidence.
- **Six offline PostgreSQL checks passed**: driver/pool arguments (mocked engine factory), TLS/port/driver rejection, private-schema/FK DDL compilation, fail-closed audit behavior, RLS flag not masking public grants (mocked catalog), and URI-error redaction. These are not live PostgreSQL tests.
- A full discovery run passed 28 tests and skipped the real PostgreSQL test; two subsequently added offline cases passed in a targeted six-case run. No live PostgreSQL assertion is counted as passed.
- `test_postgres_integration.py` is opt-in and was **skipped**: no SMARTSPEND_TEST_POSTGRES_URL plus disposable-database acknowledgement was provided. No local PostgreSQL/docker tooling was found and psycopg was not installed in the local venv during this pass. Install requirements before actual PostgreSQL commands. The opt-in test migrates/verifies an isolated private schema, reopens a persisted Decimal value and exercises real SELECT/INSERT/UPDATE/DELETE denial under anon/authenticated roles. It never falls back to production DATABASE_URL.
- Python syntax checks passed for storage, migration/verification and transfer code; `git diff --check` passed. Frontend was not changed or browser-tested in this Supabase pass.

Next operator actions: install requirements; encode the project database password without printing it; store the exact Session pooler URI only in Render/operator DATABASE_URL; run migrate and verify; optionally transfer/validate the existing SQLite ledger with writers stopped; set exact Vercel CORS origin and secure cookie settings; review the prepared Render start command. Keep deployment disabled until live privilege/connectivity checks and the browser checklist pass. See DEPLOYMENT.md for the exact sequence and safe rollback. Keep private schema excluded from Data API exposure; do not put database credentials in Vercel frontend variables.

No real .env was changed, no real/production PostgreSQL connection was made, no existing financial database was migrated, and nothing was deployed or pushed. Live Supabase ACL/RLS behavior, transfer, hosted pooler connectivity and browser/voice/cross-site-cookie behavior remain unverified until the documented commands/tests are run against the appropriate isolated/target environments.


## Backend commit preparation

Checked local main tracking origin/main and the GitHub origin remote; main was the only remote branch advertised. Render dashboard branch settings were not accessible for independent verification. Backend source/tests and deployment documentation were staged separately from frontend changes. Pre-commit full backend discovery ran 31 tests: 30 passed and the opt-in live PostgreSQL test was skipped. Staged whitespace checks passed; a credential-pattern/excluded-path scan found no matches in 26 staged files. Real .env files, databases, backups, virtual environments and all frontend implementation changes were excluded. No manual Render deployment is part of the Git commit/push operation.


## Sanitized database startup diagnostics fix

Replaced the generic database CLI failure with structured stderr JSON identifying connection/migration/security_verification, exception/driver class, validated PostgreSQL SQLSTATE and a fixed category/explanation. Raw driver messages, SQL/parameters, URIs/passwords and financial values are never emitted by the diagnostics formatter. Configuration/import failures and safe policy refusals also follow this path. A migration audit failure keeps its verification stage and still aborts the transaction; TLS enforcement, private-schema RLS, ACL checks, FastAPI ownership and existing records were not weakened or reset.

Added 12 targeted tests covering authentication, DNS/network/timeout/TLS, insufficient privileges, SQL/schema failures, SQLAlchemy wrapper/driver SQLSTATE, safe policy messages, malformed SQLSTATE, secret-bearing exception redaction, bootstrap failures, successful/nonzero CLI exit behavior, and migration/audit rollback. Full local discovery ran 43 tests: **42 passed, one isolated live PostgreSQL test skipped**. Production was not contacted and the live Render failure has not been diagnosed yet; the next attempted startup will provide the safe category/class/SQLSTATE needed to identify it.

DEPLOYMENT.md clarifies that Uvicorn must use `main:app`; the reported dashboard command used `uvicorn main`, while checked-in render.yaml already had the correct import target. Only the backend diagnostics fix/tests and related documentation are included in this commit scope. No real .env/database was changed, and no Render deployment was invoked.


## Sequence privilege audit evaluation-order fix - 19 October 2026

Confirmed an unsafe SQL expression in audit_connection: `relkind='S' AND has_sequence_privilege(...)` permits PostgreSQL's optimizer to evaluate the function for a non-sequence pg_class row. WHERE clause order or wrapping the expression in an EXISTS/subquery is not an evaluation barrier. PostgreSQL documents the expression-order rule at https://www.postgresql.org/docs/current/sql-expressions.html#SYNTAX-EXPRESS-EVAL.

Exact production change: retained the schema filter, relkind filter and role/schema bind parameters, and guarded has_sequence_privilege inside a row-dependent `CASE WHEN c.relkind = 'S' THEN ... ELSE false END`. The audit is called inside migrate_postgres before transaction commit, and separately by verify_postgres/startup. Both paths now use the guard. No RLS, ACL, ownership, TLS, version or rollback checks were removed or relaxed.

Other calls reviewed: has_table_privilege and has_any_column_privilege receive table OIDs already materialized by a completed Python catalog fetch, in separate bound SQL statements. This is an application execution boundary, not a WHERE/subquery ordering assumption; PostgreSQL cannot inline those calls into the previous catalog query. Added a maintenance comment documenting that distinction. has_schema_privilege receives the bound application-schema name, not a mixed relation OID. acldefault receives a selected object-kind code and owner-role OID, and aclexplode receives ACL arrays; neither is a relation-type-specific OID privilege call. The transfer's pg_get_serial_sequence uses explicit metadata table names, not a mixed-object catalog predicate. No additional instance of this evaluation-order hazard was found.

Added two offline tests: assert CASE placement and bound schema/role filters in the SQL actually emitted by the audit; assert forbidden sequence privileges still raise the sequence_privileges policy error. Added a real PostgreSQL regression using a confirmed disposable database with ordinary app tables and SERIAL sequences: migration and verification must complete without WrongObjectType; a temporary USAGE grant to anon must be detected specifically as sequence_privileges; a savepoint rollback restores the grant and the audit must pass again. No roles are created and no tables/data are dropped. The existing isolated-target guard is reused for both live tests.

Actual results: full backend discovery ran **46 tests: 44 passed, two live PostgreSQL tests skipped**. This includes existing diagnostics, RLS/ACL refusal, ownership, TLS configuration and rollback tests. No SMARTSPEND_TEST_POSTGRES_URL was supplied, and no local PostgreSQL/docker tooling was available. **The new real PostgreSQL WrongObjectType/forbidden-grant regression was not run**; mock SQL-shape/security tests are not live PostgreSQL evidence. Python syntax checks and backend whitespace checks passed.

To run only the new real regression later, from the backend directory with a separate disposable PostgreSQL URL and the existing explicit disposable-database confirmation configured securely:

```text
python -m unittest -v test_postgres_integration.RealPostgresTests.test_mixed_relations_and_forbidden_sequence_privileges
```

Production and the existing financial database were not contacted or changed. POSTGRES_BACKUP_CONFIRMED was not set. Raw exceptions/secrets were not printed. Unrelated frontend edits were left untouched. The follow-up commit scope is limited to this audit fix, its regression tests and this report. No deployment is part of the Git commit/push operation.

## Email authentication implementation ? 19 October 2026

This section supersedes earlier username-based signup instructions. No commit, push, deploy, production connection/data write, real .env edit, or CORS/cookie/API URL change was performed. Existing unrelated Graphite/Lime frontend work was preserved.

### Changes by screen and contract

- Login: email/password by default, native email field, email autocomplete, trimmed input, existing validation/loading/retry/password visibility/session restoration. A separate older-account toggle uses the original account ID/password only for accounts without email enrollment. Approved layout, tokens and responsive styles remain unchanged.
- Signup: Name, Email, Password and optional monthly income (empty/omitted becomes zero). Display names need not be unique. No username or fabricated credential is created for new users.
- Account: email display and an explicit ownership-not-verified statement; username-only users can enroll an email using their active session and current password. Success refreshes the user in place. Errors remain visible; incorrect current passwords do not end the session. No email editing/recovery/merging feature was added.
- API: POST /auth/signup and /auth/login use email credentials; POST /auth/legacy-login and temporary legacy-body compatibility on /auth/login are limited to unenrolled accounts. POST /auth/enroll-email accepts only email/current_password for the authenticated user. /auth/me and other UserOut responses include email and email_verified=false. Existing financial routes and ownership checks are unchanged.

### Security and migration

Server-side email-validator validates syntax without network/DNS checks, trims surrounding whitespace, ASCII-normalizes international domains, rejects non-ASCII local parts and lowercases the entire address for consistent case-insensitive lookup. Plus tags and dots are preserved. Format validation does not verify mailbox ownership. Unique email plus a canonical-value CHECK is enforced by both database dialects, including concurrent signup/enrollment races; collisions return 409 and roll back. Password hashing, dummy-hash generic login failure, session cookies, expiry and existing rate limits remain.

Schema 5 adds only email_accounts (user ID PK/FK, unique canonical email, password hash). It does not rebuild users/credentials or infer emails from account IDs. Existing sessions, IDs, financial minor-unit amounts and chat records remain. Successful enrollment copies the existing hash and disables that account's legacy login without deleting its credential/data. No matching-name/email ledger claiming or account merging is permitted. SQLite version-4 migration and repeat migration were tested on synthetic data, including preserved old credentials/session/transaction rows and the version-4 backup. PostgreSQL retains transactional migration, backup attestation for upgrades, RLS, private schema, sequence checks and fail-closed audit; live PostgreSQL upgrade execution remains unverified. POSTGRES_BACKUP_CONFIRMED was never set.

### Files changed for this request

Backend: auth.py, main.py, models.py, schemas.py, migrations.py, postgres_storage.py, enroll_legacy.py, requirements.txt; new test_email_auth.py; updated test_regressions.py, test_postgres_storage.py and test_postgres_integration.py. Frontend: AuthScreen.jsx, new EmailEnrollment.jsx, App.jsx, api.js, test-api.cjs, test-render.cjs and test-workflows.cjs. Documentation: this report, DEPLOYMENT.md and MANUAL_BROWSER_CHECKLIST.md. Other pending design edits predate this request and were preserved.

### Verification evidence

- Final backend discovery: 51 tests, 48 passed and 3 live PostgreSQL tests skipped, 47.273 seconds. No failures.
- New isolated real-HTTP tests cover syntax/normalization, plus/dot preservation, email signup/login, default income, session restoration, generic wrong/missing-account responses, duplicate casing, racing signups (one success/one 409), duplicate display names, database canonical CHECK, legacy login/enrollment, incorrect password, taken email, rejected user-ID injection, post-enrollment email login/legacy rejection, and financial/chat isolation.
- Frontend npm test: 33 passing check groups (12 API, 13 render/auth states including legacy mode, 5 overview, 3 design-system). React rendering is not real-browser verification.
- node test-workflows.cjs: 6 passing real-HTTP groups on a new temporary SQLite backend. Includes email signup/login, profile, financial CRUD/budgets/bills/imports, deterministic test-only Coco Save/Cancel, backend-restart and logout/login persistence, two-account isolation and expired multipart upload. No production writes.
- Production npm run build passed: 58 transformed modules, assets index-BINstk55.css / index-CmVUE2kn.js.
- Browser discovery returned no apps/browsers. Real desktop/mobile interaction, autofill, keyboard and email enrollment UX remain unverified; see manual checklist. No screenshots claimed.
- No isolated PostgreSQL URL was supplied. The three opt-in live PostgreSQL tests, including new unique/canonical-email constraint checks, were skipped. SQLite/offline tests are not PostgreSQL evidence. Email verification/recovery and retirement of the temporary legacy path are future work, not completed features.

### Deployment steps (not executed)

DEPLOYMENT.md contains the exact schema-5 release sequence and rollback limits. Rehearse on disposable PostgreSQL first, snapshot the real target before any upgrade, install requirements, run the PostgreSQL manage_database.py migrate and verify commands using the existing protected environment, and remove the temporary backup-attestation flag afterward. Coordinate a signup maintenance window and release backend before matching frontend; old frontend username signup and new frontend email signup cannot share the old contract. Preserve existing environment/CORS/cookies/VITE_API_URL. Existing users use older-account login, then Account enrollment with their current password; no automatic email assignment occurs. Old binaries cannot serve schema 5/email-only users: rollback requires a matched snapshot/code version with reconciliation of new writes, never lowering the version marker or deleting accounts.


## Backend-only email-auth release preparation

Reviewed schema 5 and DEPLOYMENT.md for the requested backend-only commit. Existing PostgreSQL versions 2/3/4 require a completed, restorable snapshot/export and operator backup attestation; no automatic PostgreSQL backup is created. Fresh/unchanged schema-5 runs do not need the flag. SQLite has its existing online backup/startup migration; manage_database.py is PostgreSQL-only (the earlier same-command SQLite guidance was corrected). No production connection, migration, backup flag, environment change or deployment was performed.

Only backend email-auth code/migrations/tests and relevant documentation sections are included. Pending frontend code and unrelated earlier design/CORS documentation are excluded and preserved locally. The repository's pre-update frontend uses old /users onboarding and cannot provide secured/email auth. The live Vercel revision was not inspected. A username-auth frontend retains legacy login/session compatibility for unenrolled users, but its signup is incompatible. Coordinate a separate matching frontend release before email enrollment or reopening signup. render.yaml has autoDeploy:false; actual dashboard automation was not accessed or certified.

Rollback cannot be a simple old-code redeploy: old schema guards reject version 5, and email-only accounts have no legacy credentials. Stop writers and reconcile writes before restoring a matched snapshot/code revision. Never lower version markers or delete credentials/accounts to force compatibility. Exact manual Render build/start/migration and release-gating steps are in DEPLOYMENT.md.

Backend-only release validation rerun: 51 tests in 41.639 seconds; 48 passed, 3 live PostgreSQL tests skipped (no isolated target). No failures. No frontend or production tests were run during this release preparation.

## Final empty-schema preparation after operator audit

The user supplied the production SQL audit: schema_version=4, all 10 application data tables contain zero rows, and smartspend_schema has exactly one metadata row. This is operator-reported live read-only evidence at audit time, not an agent-run PostgreSQL migration or concurrency test. It supersedes the prior "emptiness unverified" release status; a locked migration-time recheck is still required because the data may change after observation.

Re-reviewed the empty exemption: strict complete schema-4 relation set; advisory transaction lock; READ COMMITTED selected before queries; all application relations plus version marker locked SHARE ROW EXCLUSIVE with 10s timeout; version/catalog/full-visibility recheck; any data row refuses no-backup upgrade; locks held through additive DDL, RLS/privilege audit and commit. Versions 2/3 remain backup-gated. Existing version-5 reruns stay repeatable. No table/schema deletion/reset, secret or environment change, or backup flag was introduced. The sole DELETE remains the pre-existing transactional replacement of the schema-version metadata row, never deletion of user records.

Strengthened mocked migration-call-path regressions: empty schema 4 reaches DDL and audit; populated schema 4 and older 2/3 stop before DDL; schema 5 does not request exemption; post-exemption security-audit failure propagates and rolls back; connection always closes; READ COMMITTED is first. Existing helper tests cover locks/all-table visibility/rows/partial schema/version changes/lock timeout. No live PostgreSQL migration or lock-race test was run (no test endpoint); user read-only audit results are reported separately.

Deployment remains future operator work: stop writers/signup, release a reviewed revision containing this unpushed fix (877031e alone lacks it), keep the backup flag unset for qualifying empty schema 4, run the unchanged migration/verify/main:app startup, confirm schema 5/security/health, then separately release the matching frontend with existing API configuration and verify auth/persistence/enrollment before reopening signup. If data appears, stop and take a real backup rather than setting a false attestation. Pending frontend work is preserved. No commit/push/deploy/production mutation was performed.

Final rerun after strengthening the migration-call-path mocks: 55 backend tests in 44.089 seconds; 52 passed, 3 live PostgreSQL tests skipped, no failures. The first run exposed a test fixture returning an integer version as a role name; the mock now distinguishes catalog queries. Production code did not require a change from that test failure. git diff --check passed.

## Render startup timeout investigation and local fix

Operator evidence: Render migrate/verify succeeded at schema 5 / 12 tables; no Uvicorn process/startup-complete message appeared; the last visible output was the deprecated google.generativeai SDK warning. The warning is not established as the cause. No production connection, environment/configuration edit, migration, deployment, commit or push was performed in this investigation. Schema 5, the empty-schema migration guard, full RLS/privilege/ownership checks and pending frontend work remain intact.

### Actual reproduction and cause limits

A subprocess launched with -X importtime and faulthandler.dump_traceback_later(8, repeat=True), a new temporary SQLite file, no paid AI key, and a 35-second health deadline reached actual HTTP 200 on a bound port in 7.40 seconds. Uvicorn emitted Started server process and Application startup complete; no timed stack dump fired because startup completed. Baseline cumulative import measurements: ingestion/pandas about 1.965 seconds and llm_coach/google.generativeai about 1.643 seconds. These demonstrate avoidable import overhead, not a reproduced Render deadlock. The first disposable probe encountered Windows file-handle cleanup trouble after launcher termination; subsequent test harnesses use graceful HTTP shutdown and completed cleanup successfully.

Inspection found no model/network call, model download or app-level thread join at module scope. Confirmed blocking startup work comprised eager Gemini SDK/protobuf/grpc imports, eager pandas/numpy imports, database migration/security queries before FastAPI construction, and a dummy-password scrypt hash. On PostgreSQL, main repeated the necessary full security audit after the separate CLI audit; it previously lacked a statement timeout/total audit deadline. That audit can block after the SDK warning, so the warning alone cannot identify the blocking stage. The precise Render cause (including resource pressure or remote database delay) remains unconfirmed. No live PostgreSQL/Render startup was reproduced here.

### Changes

- main.py: required database migration/audit and dummy-password hash now run in FastAPI lifespan, before any traffic can be served. PostgreSQL still verifies only, never migrates implicitly on app import. Database/security failure prevents startup. Engine resources close on shutdown. Flushed fixed-field JSON logs identify application_import, database_security and authentication start/complete/failure with elapsed times; database failure is emitted through the existing sanitized diagnostic formatter and rethrown without the raw underlying message. No secrets, SQL parameters, financial rows or raw exceptions are logged.
- llm_coach.py: optional deprecated SDK import/configure is deferred until the first AI request. One daemon initializer is shared; callers wait at most five seconds, so a stalled initializer cannot create unbounded threads or block server startup. Timeout yields a generic retry/support response; initialization failure tells the operator to check dependencies/restart. Provider request timeout remains 30 seconds with retries disabled; response limits and explicit Coco Save/Cancel behavior remain. The deprecated dependency is not migrated in this fix and its warning may still appear on first AI use.
- ingestion.py: pandas loads only for statement parsing; PDF tooling was already loaded inside the PDF parser. SMS/manual/API startup no longer imports those heavy modules. Existing import parsing behavior is covered by regressions.
- postgres_storage.py: standalone/startup verification sets transaction-local statement_timeout=15s and lock_timeout=5s. The complete existing audit checks a 45-second budget before and after each query. A query can run up to its statement limit before an expired overall budget is noticed; network failures are not a hard OS process deadline. Existing connect/pool/TLS settings are retained. Audit failure/timeout stops startup; no audit is skipped or weakened. Migration-time audit logic/rollback remains required.
- New startup_telemetry.py and test_startup.py; test_regressions.py now stubs the lazy provider explicitly rather than importing a real SDK for a unit test.

### Port/health and safety verification

The new bounded subprocess harness runs the actual Uvicorn server against its own temporary SQLite file with a deliberately synthetic AI key and a finder that raises if pandas or google.generativeai is imported. It uses import timing and scheduled stack dumps, polls the real health endpoint with a 25-second budget, checks the real HTTP 200/body and Uvicorn startup markers, then gracefully shuts down and cleans up. Healthy startup completed in 2.46 seconds. A second real-process test injects a required-database-check failure: the server does not serve health or reach startup complete, emits failure diagnostics, and does not print injected private values. Test-only shutdown routes exist only in the subprocess harness, not production main.py.

The first full regression run passed: 59 tests, 56 passed / 3 live PostgreSQL skipped, 50.133 seconds. After adding provider-initialization-failure and verification-query-bound checks, all six targeted startup tests passed in 5.343 seconds, including another actual port/health HTTP 200 at 2.46 seconds. Existing auth/persistence/isolation, CSV/PDF imports, chat confirmations, migrations and audit tests passed in the full run. PostgreSQL timeout configuration/deadline tests are mocked, not live PostgreSQL evidence. No browser/frontend checks or provider network call was performed for this backend fix. Render-specific resource/connection behavior remains unverified until an authorized release.

The existing Render build/start/root and all DATABASE_URL/CORS/cookie settings remain unchanged. On a future authorized release, compare the flushed stage logs with Uvicorn markers: application_import completes before Uvicorn starts the ASGI lifespan; database_security and authentication must complete before Application startup complete and traffic acceptance. A failure should be diagnosed from its sanitized stage/category rather than bypassing the audit or increasing the port timeout blindly. Pending frontend edits were preserved.

Final complete suite after all startup changes: 61 tests in 49.923 seconds; 58 passed and 3 live PostgreSQL tests skipped, no failures. Actual isolated Uvicorn port/health HTTP 200 again after 2.46 seconds. git diff --check passed. No production verification or deployment is claimed.
