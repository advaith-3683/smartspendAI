# Local browser verification — not yet performed

Browser discovery on 19 October 2026 returned no browser or native-app surfaces. None of the browser checks below is marked passed. Earlier HTTP tests and React render checks are separate evidence, not browser verification.

## Safe isolated setup

Use two new PowerShell terminals at the SmartSpend repository root. Do not edit any `.env` file. In **terminal A**, create a new disposable database and start only the test backend:

```powershell
$browserTestDir = Join-Path ([IO.Path]::GetTempPath()) ('smartspend-browser-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $browserTestDir | Out-Null
$env:DATABASE_URL = 'sqlite:///' + (Join-Path $browserTestDir 'browser-test.db').Replace('\', '/')
$env:APP_ENV = 'development'
$env:COOKIE_SECURE = 'false'
$env:COOKIE_SAMESITE = 'lax'
$env:CORS_ORIGINS = 'http://127.0.0.1:5174'
$env:GEMINI_API_KEY = ''
Write-Host "ISOLATED TEST DATABASE: $env:DATABASE_URL"
& '.\smartspend backend\venv\Scripts\python.exe' -m uvicorn main:app --app-dir '.\smartspend backend' --host 127.0.0.1 --port 8001 --workers 1 --no-proxy-headers
```

In **terminal B**:

```powershell
$env:VITE_API_URL = 'http://127.0.0.1:8001'
Set-Location '.\smartspend frontend'
npm.cmd run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

Open **http://127.0.0.1:5174** consistently, not a mixture of localhost and 127.0.0.1. If either port is occupied, stop and choose new matching ports/origins rather than terminating an unknown process. Keep terminal A open: restart its exact last uvicorn command without rerunning the database-creation commands, so the same test file is reused. All test entries must stay in this disposable database.

## Checklist

- [ ] **Account persistence:** Sign up as account A. In the selected month, add a Food expense of INR 12.34, a Food budget of INR 500, and an Internet bill of INR 50 due on day 4. Log out and log back in. Verify the three records and amounts remain; refresh and add a second expense. Confirm logout did not delete anything.
- [ ] **Restart and separate context:** Stop only terminal A's backend with Ctrl+C and restart the same uvicorn command with its unchanged DATABASE_URL. In a separate browser profile/private context, sign in as A. Verify expenses, budget, bill and saved chat; add another expense and check it appears in the original browser after Refresh. Clear only the test site's browser storage and sign in again to confirm the database remains authoritative.
- [ ] **Account isolation:** In the separate context sign up as B. Its ledger must not contain A's records. First confirm `/auth/me` identifies B. From the frontend's browser developer tools, make test API requests with `credentials: 'include'` and attempt A's transaction/budget/bill/history reads and A's transaction PATCH/DELETE or bill pay action using IDs from A's test records. Expect ownership-related 403/404 and no changes to A; a 401 or an Origin-not-allowed error does not demonstrate ownership enforcement. Use only these isolated test accounts and IDs.
- [ ] **Desktop/mobile UX:** At desktop width and approximately 390px mobile width, visit all six sections. Use keyboard Tab/Enter, check visible focus and labels, edit decimal amounts, search/filter/edit/delete test expenses, and pay/unpay a bill. Switch months quickly and verify old responses do not restore the previous month. Check loading/empty states, invalid values, API-offline errors and Retry. Check mobile navigation and Account logout remain usable, with tables scrolling inside their panels.
- [ ] **Imports:** Paste a test debit SMS; edit the preview and import it once. Upload a small CSV with `Date,Description,Credit Amount,Debit Amount`, one salary credit and one cafe debit. Verify only the debit is proposed. Edit date, merchant, category and amount before saving. Check ambiguous unsigned amounts/invalid dates, an unsupported file and an oversized file show useful errors. Retry the same displayed batch after a simulated lost response and confirm no duplicate expense. Separately reparsing a file is a new batch, not historical deduplication.
- [ ] **Coco and voice:** With the default blank test API key, verify a useful unavailable-AI message and no expense insertion. Successful chat/proposal verification requires a working Gemini key: set it only in terminal A's process environment, without changing `.env` or sharing the key, and restart the same backend/database. This can consume provider quota. Ask to record an expense; confirm it appears only as a proposal, **Cancel** adds no spending, and **Save** adds exactly one. Refresh/logout/login and check chat and pending proposals persist. Where the browser supports speech recognition, explicitly allow microphone access and test real speech, stop/review/Send, spoken replies and leaving Coco. **Microphone permission, hardware, transcription accuracy and audio playback require manual human testing.** Unsupported voice controls must not prevent text chat.

Record browser/version, viewport, result and any failure for each item before deployment. Then stop both test servers. Retain the isolated test database for diagnosis or remove only its printed temporary directory after confirming its path. Do not run these checks against your financial database.


## Frontend follow-up on 19 October 2026

Still unverified in a real browser: no browser surfaces were available. The frontend's isolated HTTP tests now cover account persistence across a genuinely fresh backend process, two cookie jars, ownership denials, multipart expiry and stubbed Coco proposals; they do not prove browser cookie/CORS behavior or layout.

Also check: block cookies and confirm login explains session failure; expire/revoke the session while uploading and confirm private content clears; switch accounts in another tab and focus the original tab; disconnect the API during chat reset and verify saved history stays visible; deny microphone permission and verify typed chat still works. Dictation must fill the message box for review, without automatically sending. Confirm transaction deletion, bill deletion/unpay and conversation reset have keyboard-operable confirmation. Check narrow 320px and 390px layouts and verify the page itself does not scroll horizontally (tables may scroll inside their panels).


## Ivory/emerald design and localhost CORS follow-up

The actual error origin is http://localhost:5173, whose live Render GET/OPTIONS probes lack Access-Control-Allow-Origin. Before a later authorized live test, append that exact origin to Render's existing comma-separated CORS_ORIGINS and restart the backend, preserving existing origins and production cookie security. Do not run write tests against the real ledger. DEPLOYMENT.md contains the safe isolated-local setup alternative and exact dashboard instructions.

For the new light interface, check login/signup at 1440px, 768px, 390px and 320px. On mobile, the compact brand and form should appear without the large introduction/illustration. Show/Hide must preserve the password and focus; only signup should show password requirements. Block the isolated backend network request, confirm the alert is inside the form panel, then restore the server and use Retry. An unauthenticated /auth/me 401 must show ordinary sign-in, not a network error. Test 500/timeout separately; do not assume cookie blocking from a fetch error.

For all six workspace pages, check real-data charts, table-only horizontal scrolling, focus rings, form errors and notifications on ivory/white surfaces. The styled confirmation dialog must focus Keep it, contain Tab focus, cancel on Escape, and return focus to its invoking control; Confirm alone should perform the requested deletion/unpay/reset. Recheck Coco Save/Cancel and voice manually. No browser screenshot, console, viewport or keyboard checks were possible during implementation; do not mark them passed based on the Node render/HTTP tests.


## MediFlow source-derived redesign: required visual sign-off

The current reference is the accessible MediFlow frontend source at C:/Users/advai/OneDrive/Desktop/Mediflow-AI/frontend. Its deployed URL could not be visually inspected. The previous ivory/emerald instructions are superseded by the source's navy authentication panel, blue actions, slate canvas, white surfaces and teal AI accents.

When a browser is available, FIRST compare MediFlow and SmartSpend login/dashboard at 1440px and 390px, and capture screenshots of SmartSpend login and dashboard at both sizes. Check source parity in typography, navy/blue/slate tokens, auth proportions, grouped metrics, section hierarchy and spacing before inspecting the other pages. Then inspect Transactions (ledger/entry/import), Budgets & Bills, Goals & Insights, Account and Coco at 320px, 390px, 768px and desktop. Do not consider the build, server-render output or fixture tests a substitute for this review.

Check mobile drawer open/close, Escape and Tab containment, focus return, and resizing to desktop while open. Verify Add transaction opens the entry form and focuses Amount; View all opens the ledger. Confirm desktop tables become labelled mobile rows without page overflow, and editable import tables scroll within their labelled region. Check profile editing, Coco multiline Send/Shift+Enter and IME behavior, voice review, saved history/proposals and explicit Save/Cancel. Re-test session expiry, styled connection errors/Retry, deletion confirmations and two-account persistence using the isolated backend only. Record browser/version, screenshots, viewport and findings. All these visual/interactive checks remain unverified in this environment.


## Approved production Design A rollout

Earlier unapproved palette/layout guidance is superseded. Review the real working application at http://localhost:5173/ using the approved full-screen Graphite & Lime direction. Check authentication plus all six workspace screens at 1920x1080, 1440x900 and 390x844, then at 200% browser zoom and short-screen/mobile-keyboard conditions. Screenshots were unavailable during implementation.

Confirm the auth masthead/promotion and real form match full-screen A (no variant/demo controls), and that signup/errors scroll naturally without clipping. Check computed body/input text 16-18px and supporting text >=14px, accessible focus, readable currency, visible Add transaction, graphite chart/table/dialog surfaces, semantic status labels and independent income/expense colors. Inspect no horizontal page overflow; tables should become labelled mobile rows while editable import previews scroll inside their region. Exercise sidebar/drawer and dialog focus/Escape/return, profile errors/success, Coco Send/dictation review and Save/Cancel. Use only the isolated local backend setup above for writes and account-isolation testing. Build, source-token contrast and HTTP tests passed, but are not a substitute for these real browser checks.


## Email transition checks (not browser-verified)

Use only the disposable setup above, never the live backend. Register Name/Email/Password with monthly income blank; verify zero income and email display. Test native email validation, casing/outer whitespace, password visibility, mobile keyboard, autofill and visible loading/errors. Verify duplicate case variants fail, same display names succeed, incorrect login stays generic, refresh/session restoration and logout/login retain records. On a synthetic legacy account use older-account sign-in, add email under Account using the current password, test wrong-password/taken-email errors, then verify existing session/data remain and only email login works afterward. Verify a second account cannot read/update/delete the first account's records. No test here proves mailbox ownership. These checks are pending real-browser execution.
