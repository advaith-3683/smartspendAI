const { buildSync } = require('esbuild')
const { resolve } = require('node:path')
const Module = require('node:module')
const assert = require('node:assert/strict')
const React = require('react')
const { renderToString } = require('react-dom/server')
const originalState = React.useState
const bundle = buildSync({ entryPoints: [resolve('src/App.jsx')], bundle: true, write: false, platform: 'node', format: 'cjs', packages: 'external', define: { 'import.meta.env': '{}' }, loader: { '.css': 'empty' } }).outputFiles[0].text
const mod = new Module(resolve('render-smoke.generated.cjs'), module)
mod.filename = resolve('render-smoke.generated.cjs')
mod.paths = module.paths
mod._compile(bundle, mod.filename)
const App = mod.exports.default
for (const view of ['restoring', 'login', 'overview', 'transactions', 'budgets', 'coach', 'planning', 'settings']) {
  let index = 0
  React.useState = (initial) => {
    const current = index++
    if (current === 0) initial = view === 'login' ? null : { id: 1, name: 'Smoke Test', monthly_income: 1000 }
    if (current === 1) initial = view === 'restoring'
    if (current === 11) initial = true
    if (current === 7) initial = view
    return originalState(initial)
  }
  try {
    const html = renderToString(React.createElement(App))
    assert.ok(html.length > (view === 'restoring' ? 10 : 100))
    if (view === 'restoring') { assert.ok(html.includes('Restoring your account')); assert.ok(!html.includes('Main navigation')); console.log('PASS restoration hides private content'); continue }
    if (view === 'login') assert.ok(html.includes('autoComplete="current-password"'))
    else { assert.ok(html.includes('Main navigation')); assert.ok(html.includes('main-content')); assert.ok(html.includes('Log out of this session')); assert.ok(html.includes('workspace-topbar')); assert.ok(html.includes('aria-label="Open navigation"')); assert.ok(html.includes('workspace-navigation')) }
    console.log(`PASS rendered ${view}`)
  } finally { React.useState = originalState }
}

const authBundle = buildSync({ entryPoints: [resolve('src/components/AuthScreen.jsx')], bundle: true, write: false, platform: 'node', format: 'cjs', packages: 'external', define: { 'import.meta.env': '{}' }, loader: { '.css': 'empty' } }).outputFiles[0].text
const authModule = new Module(resolve('auth-render.generated.cjs'), module)
authModule.filename = resolve('auth-render.generated.cjs'); authModule.paths = module.paths; authModule._compile(authBundle, authModule.filename)
for (const variant of ['login', 'signup', 'connection', 'visible-password', 'legacy']) {
  let index = 0
  React.useState = initial => {
    const current = index++
    if (current === 0) initial = variant === 'signup'
    if (current === 5) initial = variant === 'visible-password'
    if (current === 8) initial = variant === 'legacy'
    return originalState(initial)
  }
  try {
    const html = renderToString(React.createElement(authModule.exports.default, { sessionError: variant === 'connection' ? 'Server origin unavailable' : '', onRetrySession: () => {}, onCreated: () => {} }))
    assert.ok(html.includes('auth-form-panel')); assert.ok(html.includes('intro-column')); assert.ok(html.includes('auth-form-wrap')); assert.ok(html.includes('finance-motif')); assert.ok(html.includes('auth-grid')); assert.ok(!html.includes('preview_user')); assert.ok(!html.includes('Design preview')); assert.ok(html.includes('<form')); assert.ok(!html.includes('readonly=""')); assert.equal((html.match(/<h1(?:\s|>)/g) || []).length, 1)
    assert.ok(!html.includes('operator'))
    if (variant === 'legacy') assert.ok(html.includes('Legacy account ID') && html.includes('autoComplete="username"'))
    else { assert.ok(html.includes('type="email"')); assert.ok(html.includes('autoComplete="email"')); assert.ok(!html.includes('>Username<')) }
    assert.ok(html.includes('aria-label="Show password"') || html.includes('aria-label="Hide password"'))
    if (variant === 'signup') { assert.ok(html.includes('new-password')); assert.ok(html.includes('password-help')); assert.ok(html.includes('autoComplete="name"')) }
    else assert.ok(!html.includes('12–128'))
    if (variant === 'connection') { assert.ok(html.indexOf('Server origin unavailable') > html.indexOf('auth-form-panel')); assert.ok(html.includes('role="alert"')); assert.ok(html.includes('Retry')) }
    if (variant === 'visible-password') assert.ok(html.includes('type="text" required="" maxLength="128"'))
    console.log(`PASS authentication ${variant} state`)
  } finally { React.useState = originalState }
}

for (const [code, status, title] of [
  ['network', undefined, 'Connection unavailable'], ['timeout', undefined, 'Connection timed out'],
  ['http', 503, 'Service unavailable'], ['authentication', 401, 'Sign-in not accepted'],
  ['protocol', 200, 'Unexpected server response'], ['session', 401, 'Session could not be restored'],
  ['validation', 422, 'Check your sign-in details'], ['rate_limit', 429, 'Too many attempts'],
]) {
  const error = Object.assign(new Error('Isolated authentication error'), { code, status })
  const html = renderToString(React.createElement(authModule.exports.ConnectionAlert, { message: error, onRetry: () => {} }))
  assert.ok(html.includes(title), `Missing ${code} error title`)
  assert.ok(html.includes('Isolated authentication error') && html.includes('Retry'))
  if (code !== 'network') assert.ok(!html.includes('Connection unavailable'))
}
assert.equal(renderToString(React.createElement(authModule.exports.ConnectionAlert, { message: null })), '')
console.log('PASS login banners distinguish network, timeout, HTTP, auth, session, validation and protocol errors')

const widgetBundle = buildSync({ stdin: { contents: `
  export { default as BudgetCard } from './src/components/BudgetCard.jsx'
  export { default as WeeklyDigest } from './src/components/WeeklyDigest.jsx'
  export { default as HomeVoiceEntry } from './src/components/HomeVoiceEntry.jsx'
`, resolveDir: process.cwd(), loader: 'jsx' }, bundle: true, write: false, platform: 'node', format: 'cjs', packages: 'external', define: { 'import.meta.env': '{}' } }).outputFiles[0].text
const widgetModule = new Module(resolve('widget-render.generated.cjs'), module)
widgetModule.filename = resolve('widget-render.generated.cjs'); widgetModule.paths = module.paths
widgetModule._compile(widgetBundle, widgetModule.filename)
const widgets = widgetModule.exports
const budget = renderToString(React.createElement(widgets.BudgetCard, { pace: { category: 'Food', status: 'on_track', monthly_limit: 100, spent_so_far: 25, projected_spend: 50, percent_of_budget_projected: 50, days_elapsed: 15, days_in_month: 30 } }))
assert.ok(budget.includes('of budget projected · Day'))
assert.ok(!budget.includes('projected ? Day'))
console.log('PASS budget progress uses the intended separator')

let digestState = 0
React.useState = value => originalState(digestState++ === 0 ? { total_this_week: 20, total_last_week: 10, period_start: '2026-10-01', period_end: '2026-10-07', digest_text: 'Fixture summary', top_categories: [], bills_due_soon: [{ id: 1, name: 'Broadband', due_date: '2026-10-08', status: 'due', amount: 50 }] } : value)
try {
  const digest = renderToString(React.createElement(widgets.WeeklyDigest, { userId: 1 }))
  assert.ok(digest.includes(' · ') && !digest.includes(' ? '))
  assert.ok(digest.includes('Broadband') && digest.includes('2026-10-08') && digest.includes('due'))
  console.log('PASS weekly bill reminders retain their values and use middle-dot separators')
} finally { React.useState = originalState }

for (const state of ['failed', 'loading']) {
  let index = 0
  React.useState = value => {
    const current = index++
    if (current === 9 && state === 'failed') value = 'Could not load saved expense proposals. Please retry.'
    if (current === 10 && state === 'loading') value = true
    return originalState(value)
  }
  try {
    const home = renderToString(React.createElement(widgets.HomeVoiceEntry, { userId: 1, year: 2026, month: 10 }))
    if (state === 'failed') assert.ok(home.includes('role="alert"') && home.includes('Could not load saved expense proposals') && home.includes('Retry saved proposals'))
    else assert.ok(home.includes('Loading saved expense proposals...') && !home.includes('Could not load saved expense proposals'))
    console.log(`PASS saved-proposal ${state} state is visible and actionable`)
  } finally { React.useState = originalState }
}
