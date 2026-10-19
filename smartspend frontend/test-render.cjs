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
