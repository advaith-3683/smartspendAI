# Local browser verification — not yet performed

Browser discovery on 18 October 2026 returned no browser or native-app surfaces. None of the browser checks below is marked passed. Earlier HTTP tests and React render checks are separate evidence, not browser verification.

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
- [ ] **Coco and voice:** With the default blank test API key, verify a useful unavailable-AI message and no expense insertion. Successful chat/proposal verification requires a working Gemini key: set it only in terminal A's process environment, without changing `.env` or sharing the key, and restart the same backend/database. This can consume provider quota. Ask to record an expense; confirm it appears only as a proposal, **Cancel** adds no spending, and **Save** adds exactly one. Refresh/logout/login and check chat and pending proposals persist. Where the browser supports speech recognition, explicitly allow microphone access and test real speech, stop/send, spoken replies and leaving Coco. **Microphone permission, hardware, transcription accuracy and audio playback require manual human testing.** Unsupported voice controls must not prevent text chat.

Record browser/version, viewport, result and any failure for each item before deployment. Then stop both test servers. Retain the isolated test database for diagnosis or remove only its printed temporary directory after confirming its path. Do not run these checks against your financial database.

## Email transition checks (not browser-verified)

Use only the disposable setup above, never the live backend. Register Name/Email/Password with monthly income blank; verify zero income and email display. Test native email validation, casing/outer whitespace, password visibility, mobile keyboard, autofill and visible loading/errors. Verify duplicate case variants fail, same display names succeed, incorrect login stays generic, refresh/session restoration and logout/login retain records. On a synthetic legacy account use older-account sign-in, add email under Account using the current password, test wrong-password/taken-email errors, then verify existing session/data remain and only email login works afterward. Verify a second account cannot read/update/delete the first account's records. No test here proves mailbox ownership. These checks are pending real-browser execution.
