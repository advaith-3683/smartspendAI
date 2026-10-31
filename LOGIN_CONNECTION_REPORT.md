# Login connection investigation — 31 October 2026

## Verified production behavior

Frontend: https://smartspend-ai-indol.vercel.app

Backend: https://smartspend-backend-lsk5.onrender.com

The reported production connection failure was **not reproduced** in a fresh browser during this investigation. The existing production login page loaded without the connection banner. An expected signed-out 401 is handled normally. No production account was created, no real credentials were submitted, and no deployment or dashboard setting was changed.

| Probe | Status | Response / relevant headers |
| --- | --- | --- |
| `GET /` on Render | 200 | `{"status":"SmartSpend AI backend running"}` |
| `GET /auth/me`, production frontend Origin | 401 | `{"detail":"Please log in"}` |
| `OPTIONS /auth/login`, POST + content-type preflight | 200 | `OK` |
| `POST /auth/login`, empty validation-only JSON object | 422 | Missing email/username/password validation errors |

The authentication responses include `Access-Control-Allow-Origin: https://smartspend-ai-indol.vercel.app` and `Access-Control-Allow-Credentials: true`. The preflight permits POST and content-type. These HTTP probes completed in approximately 0.7–1.2 seconds; the client deadline is 60 seconds. A real browser could read the 401 body with `credentials: include` and produced no page JavaScript exception. An unrelated request failure from the previously closed local preview was excluded from production evidence.

The served production asset `/assets/index-CmVUE2kn.js` embeds the correct HTTPS Render API URL and credentialed fetch. Both hosting providers report production commit `6452bcb99f4dd8de4966fbea3b0d92f90ab72506`. Render's authentication logs show successful POST login followed by GET session checks, including 30 October. The targeted 18–31 October authentication 400/500/502/503 log search returned no matches; that does not exclude browser-only failures or gateway failures absent from application logs.

The Vercel environment/project metadata requests were denied with 403 for team tri-tech3. The deployed bundle proves the effective API URL, but the dashboard variable scopes could not be independently inspected. Render MCP confirms the service URL and live deployment; its available read tools did not expose cookie/environment-variable values. Successful authenticated browser behavior and actual production Set-Cookie flags were not retested without user credentials.

## Request flow and confirmed defects

On page load, `App` calls `api.me()` → credentialed `GET /auth/me`. A normal 401 shows the login form. Other restoration failures previously became a string passed to an alert always titled **Connection unavailable**.

On submission, `AuthScreen` calls credentialed JSON `POST /auth/login` (or the existing signup/legacy endpoint), followed by `GET /auth/me`. The second request verifies that the browser retained the session cookie before showing private content. A rejected login and a rejected restored session remain separate failures.

Two error-reporting defects were reproduced and fixed:

1. The API client's broad TypeError catch treated response-processing errors as transport failures. For example, an HTTP 503 with a JSON `null` error body caused `detail.detail` to throw and incorrectly produced the quoted network message. Null/irregular validation bodies are now parsed defensively, and only fetch rejection is classified as a transport/browser-policy failure. HTTP status is retained.
2. Session restoration discarded error metadata and the login banner called all failures connection errors. Error code/status now reach the login screen so HTTP, authentication, authorization, validation, rate-limit, protocol, session, timeout and network failures are distinguishable. Abort-related TypeErrors are classified as timeouts.

Separately, the current **local** Vite environment resolves production-mode `VITE_API_URL` to `http://localhost:8000`. Serving that local build reproduced `GET http://localhost:8000/auth/me` connection refusal when that backend was absent. This does not describe the deployed Vercel bundle, which correctly targets Render. Local development settings were preserved; the final release build was verified with a process-only `VITE_API_URL=https://smartspend-backend-lsk5.onrender.com` override.

The exact historical cause of the user's production transport failure remains unverified. The evidence does not justify changing production CORS, replacing the backend URL, weakening cookies, extending the timeout, or introducing automatic login retries.

## Changes limited to this investigation

- `smartspend frontend/src/api.js`: classify failures, retain status/path, parse malformed error responses defensively, trim public API URL whitespace, preserve credentials/session reset/deadline behavior.
- `smartspend frontend/src/App.jsx`: retain typed restoration errors for the login screen, clear them on retry/logout/success.
- `smartspend frontend/src/components/AuthScreen.jsx`: distinct error titles; distinguish accepted sign-in with failed cookie/session restoration.
- `smartspend frontend/test-api.cjs`: response/null/validation/error-code/timeout regressions.
- `smartspend frontend/test-render.cjs`: error-banner classifications.
- This report.

No backend, Coco, Gemini, AI initialization, Home voice, responsive CSS, database, secret, or hosting configuration changes were made in this investigation. Hashes of backend main.py, llm_coach.py and frontend CoachPanel.jsx match the start of this task. Earlier unrelated workspace edits remain present and must not be included accidentally in a login-only release.

## Verification

- Frontend production build: passed, including explicit production API URL build.
- `npm test`: passed (API, render, overview, design and existing voice suites).
- `python -B -m unittest discover -s "smartspend backend" -p test_email_auth.py -v`: all four tests passed against disposable SQLite only.
- Seven mocked-browser login scenarios passed: normal signed-out 401/no banner; HTTP 503/null; invalid JSON/HTML success response; transport rejection; invalid-credential 401; accepted login followed by session 401; retry after session failure. Mocked credentials never reached production.
- `git diff --check`: passed.

## Release / dashboard steps

No production dashboard correction is established as necessary by the current probes. Publish the login-only frontend changes with a new Vercel production build. **Do not deploy the entire current dirty workspace**: it contains earlier unrelated changes. App.jsx contains both earlier edits and this login fix, so select only the login hunks in the release.

In Vercel project **smartspend-ai → Settings → Environment Variables**, confirm the Production value (set it only if missing/wrong):

```text
VITE_API_URL=https://smartspend-backend-lsk5.onrender.com
```

Vite embeds this at build time. Variable changes require a **new Vercel deployment**; they do not alter an existing bundle. Root directory remains `smartspend frontend`, build `npm run build`, output `dist`.

No Render deployment is needed for these frontend-only changes. Preserve the existing working CORS/cookie settings. If a later probe actually shows a missing CORS grant, add the exact origin `https://smartspend-ai-indol.vercel.app` to the existing comma-separated CORS_ORIGINS list, retaining other trusted origins; no wildcard or trailing slash. Use Render **Save and deploy** to apply a runtime-variable change. For separate HTTPS Vercel/Render origins, the existing cookie design requires COOKIE_SECURE=true and COOKIE_SAMESITE=none; verify rather than changing them speculatively. Do not change database/AI settings.

After release: a signed-out page load should show GET /auth/me 401 with the allowed-origin/credential headers and no connection banner. A real login should show OPTIONS 200, POST /auth/login 200, a Secure/HttpOnly session cookie, and subsequent GET /auth/me 200. Invalid credentials should remain 401 with a sign-in error. If the original browser still fails, capture its failed request URL, browser failure reason/HTTP status, Origin and timestamp; do not share passwords or cookies.
