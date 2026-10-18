# SmartSpend AI

A personal expense tracker and Coco coach built with React/Vite, FastAPI, SQLAlchemy, and persistent SQL storage.

## Supabase deployment preparation

The current target is Vercel frontend + Render Oregon backend + Supabase Oregon PostgreSQL, using the **Session pooler on 5432**. Keep FastAPI authentication. Use `postgresql+psycopg://` with a percent-encoded database password and `sslmode=require`. Only the private `smartspend` schema is used; the frontend does not connect to Supabase. See [DEPLOYMENT.md](DEPLOYMENT.md) for the authoritative migration, RLS/privilege audit, Render settings, optional SQLite transfer and rollback steps. Older Neon/default-schema instructions in historical reports are superseded.

From the backend directory with the target URI securely in DATABASE_URL: `python manage_database.py migrate`, then `python manage_database.py verify`. Neither command transfers existing SQLite records. PostgreSQL application startup only verifies; it does not create tables. The prepared Render start command explicitly migrates/verifies before starting Uvicorn. No hosted connection, deployment or transfer has been performed here.

## Account and data behavior

Each account owns its transactions, budgets, bills, saved Coco history and pending expense proposals in the backend database. Browser storage is not the ledger. Authentication uses a 24-hour HttpOnly session cookie; only a hash of its random token is stored in the database. Passwords use salted scrypt (N=32768, r=8, p=3).

Logout deletes only the session. It never deletes an account, transaction, budget, bill, proposal or chat. Sign in with the same username/password from another browser or device to load the same ledger. Restarting the backend or refreshing a page retains data when the same persistent database is used. Redeploy persistence requires hosted PostgreSQL or SQLite on a real persistent disk: see [DEPLOYMENT.md](DEPLOYMENT.md).

## Local run (PowerShell)

Use your existing `.env`; `.env.example` is a reference and contains no secrets. From `smartspend backend`:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

From `smartspend frontend`:

```powershell
npm.cmd ci
npm.cmd run dev
```

Open `http://localhost:5173`. By default, SQLite uses a stable absolute path beside `database.py`. If an existing `DATABASE_URL` is configured, it takes precedence; retain the actual existing database path. Avoid relative SQLite URLs when changing working directories.

## Existing data and migrations

Stop old backend processes before starting the new version. Migration version 4 backs up an existing SQLite file as `*.db.backup-<UTC timestamp>` before changes. SQLite startup is serialized, and conversion/schema/version changes commit atomically. Versions below 2 convert rupees to whole minor units exactly once, using HALF_UP rounding. Later migrations add authentication, sessions, expense proposals and import retry records without dropping or recreating financial tables. Existing users, financial records and stored chats are retained.

New money columns use BIGINT minor units, decoded to Decimal for calculation. Existing SQLite FLOAT-affinity columns retain exactly representable whole cents within the supported bounds. Sums use individual Decimal values rather than floating SQL aggregates. Each input is bounded to INR 1 billion and at most two decimal places. Money out of bounds stops migration for operator review.

Do not run old code against a migrated database. To roll back, stop every process, keep a copy of the migrated file, and restore the complete pre-migration backup together with the matching old code. Never lower `PRAGMA user_version` or convert money twice. Backups contain private financial data and are ignored by Git.

Legacy owners cannot claim records publicly using a name, ID or unverified email. An operator must establish ownership outside the app, then run from the backend directory:

```powershell
.\venv\Scripts\python.exe enroll_legacy.py 123 chosen_username --verified-owner
```

Replace `123` with the externally verified ledger ID. Hidden prompts collect the password. Enrollment refuses duplicate usernames/already enrolled users and does not move or delete records. Signup creates a separate ledger. Email verification and forgotten-password flows are not simulated.

## Workspace

- **Overview:** income, actual incurred spending, remaining income, projected spending, actual category breakdown including unbudgeted categories, current overdue/upcoming reminders and quick actions.
- **Transactions:** selected-month ledger, search/category/frequency filters, add/edit/delete, SMS/statement preview and reviewed imports.
- **Budgets & Bills:** explicit category budgets, progress/projections and recurring paid/unpaid actions.
- **Goals & Insights:** conservative savings plans, subscriptions, selected-period anomalies and weekly digest.
- **Coco:** account-backed chat and voice controls. Expense tools create persisted proposals only. Save records one expense; Cancel records none. Repeating Save does not duplicate spending.
- **Account:** profile/income editing and session logout.

Desktop sidebar and compact mobile navigation share the same features. Focus states, labels, loading/error/empty states and success feedback are included. No fabricated financial data is seeded into screens.

## Financial semantics

Positive amounts are required for expenses, bills, purchases and budgets; income can be zero. Dates/months/years/due days, allowed source/frequency values and text lengths are validated on the server. Categories are normalized without replacing meaningful names or inventing budgets. Missing budgets remain explicit.

Only `daily` expenses are extrapolated in projections; `monthly` and `one_time` expenses count once. Future-dated entries remain scheduled in the ledger and are excluded from incurred totals. Past months use actual totals; future months have no incurred projection. `over_budget` means actual overspending; `at_risk` reflects projected risk/85% proximity. Overall projection sums budgeted category projections plus incurred unbudgeted amounts, labeled accordingly.

Bill days clamp to month length. Pay/unpay are atomic and serialized with SQLite write locks or PostgreSQL row locks. Deleting a payment expense clears its bill status. Deleting a recurring template keeps historical expenses; marking unpaid intentionally removes that occurrence's linked expense. Linked bill-payment transactions must be managed through bill actions rather than ordinary edits. Bill reads/payments never create budgets.

Savings use the previous three full calendar months, including zero-spend months, excluding the current incomplete month and future entries. Inadequate coverage is labeled provisional and cannot produce a supported achievable claim. Rent/EMI/insurance/tuition keywords and recurring-bill categories are protected; discretionary cuts cap at 60%.

Weekly digest totals exclude `monthly` recurring payments and say so. A zero prior-week total has no percentage comparison. Weekly spikes appear only for the current selected month. Reminders cover unpaid occurrences since a bill template's creation month through seven days ahead, including month boundaries.

## Imports and AI limits

Explicit debit/withdrawal columns take precedence over generic amounts; credit/deposit/balance columns cannot become debit columns. Generic negative signed amounts are expenses; positives are skipped. Explicit DR/debit/withdrawal/expense types import, while CR/credit/deposit/income types do not. Ambiguous unsigned rows are skipped. Review bank conventions before committing.

Previews allow selecting rows and editing date, merchant, category and amount. Invalid explicit dates are skipped; undated SMS defaults to today. CSV dates accept ISO and defined day-first formats. Keyword categorization is local; unknown merchants remain Uncategorized. Table-based PDFs are supported; scanned/encrypted/unusual layouts can need conversion to CSV.

The UI assigns each parsed batch a stable retry key. Repeating its commit after a lost response inserts only once. Separately parsing/importing the same statement creates a new batch and is not automatically deduplicated against historical transactions.

Limits: 5 MiB file, 6 MiB total body, 30 PDF pages, 500 statement rows/commit transactions, 100,000 SMS characters, 4,000 chat characters, latest 100 chat messages returned, 20 turns/20,000 characters of model history, 10 proposals per response and at most 100 pending proposals. Older stored chats are retained.

Gemini has a 30-second timeout, retries disabled, 1,200 output-token cap and 8,000-character response cap. Savings/digest figures remain available if AI narration fails. The inherited `google-generativeai` dependency is deprecated; live Gemini compatibility remains unverified. No paid service is required for core tracking, persistence, imports or deterministic planning.

Rate limits are per client IP, in-process: 10 auth requests/minute, 10 AI/import/goal/history requests/minute, 180 other requests/minute. Proposal review actions use the general limit. Use one worker, or add a shared gateway/limiter before scaling. Configure trusted proxy handling and server body/time limits explicitly.

## Verification

```powershell
# Repository root: isolated databases, mock AI, ephemeral local HTTP server
& '.\smartspend backend\venv\Scripts\python.exe' -m unittest discover -s 'smartspend backend' -p test_regressions.py -v
# Frontend directory
npm.cmd run build
node test-render.cjs
node test-api.cjs
```

See [COMPLETION_REPORT.md](COMPLETION_REPORT.md) for actual results and unverified deployment/browser integrations. No deployment or push is performed by these commands.
