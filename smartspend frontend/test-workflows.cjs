// Real HTTP/API-client coverage. No browser or production database is used.
const { buildSync } = require('esbuild')
const { resolve, join } = require('node:path')
const { mkdtempSync, rmSync } = require('node:fs')
const { tmpdir } = require('node:os')
const { spawn } = require('node:child_process')
const { once } = require('node:events')
const { randomUUID } = require('node:crypto')
const net = require('node:net')
const Module = require('node:module')
const assert = require('node:assert/strict')
const originalFetch = global.fetch
const temporary = mkdtempSync(join(tmpdir(), 'smartspend-frontend-'))
let server
let base
let cookie = ''
const events = []
global.window = { dispatchEvent: event => events.push(event.type) }

async function start(port) {
  const identity = randomUUID()
  const code = `import uvicorn, main
def fake_chat(*args, **kwargs):
    kwargs['log_expense_fn'](amount=12.34, category='Food', txn_date='2026-10-10')
    return 'Review the proposed expense before saving.'
main.llm_coach.chat_reply = fake_chat
config = uvicorn.Config(main.app, host='127.0.0.1', port=${port}, log_level='critical', access_log=False)
runner = uvicorn.Server(config)
@main.app.get('/__test_identity')
def identity(): return {'identity': '${identity}'}
@main.app.post('/__test_shutdown')
def shutdown():
    runner.should_exit = True
    return {'stopping': True}
runner.run()`
  server = spawn(resolve('../smartspend backend/venv/Scripts/python.exe'), ['-c', code], {
    cwd: resolve('../smartspend backend'), stdio: 'ignore',
    env: { ...process.env, PYTHONUTF8: '1', DATABASE_URL: `sqlite:///${join(temporary, 'isolated.db').replaceAll('\\', '/')}`,
      APP_ENV: 'development', COOKIE_SECURE: 'false', COOKIE_SAMESITE: 'lax', GEMINI_API_KEY: '', CORS_ORIGINS: 'http://localhost:5173' },
  })
  for (let i = 0; i < 100; i++) {
    if (server.exitCode !== null) throw new Error('Isolated backend failed to start; output suppressed.')
    try { if ((await (await originalFetch(base + '/__test_identity')).json()).identity === identity) return } catch {}
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  throw new Error('Isolated backend startup timed out')
}
async function stop() {
  if (server && server.exitCode === null) {
    const exit = once(server, 'exit')
    await originalFetch(base + '/__test_shutdown', { method: 'POST' })
    let timeout
    try { await Promise.race([exit, new Promise((_, reject) => { timeout = setTimeout(() => reject(new Error('Test server did not stop gracefully')), 10000) })]) }
    finally { clearTimeout(timeout) }
  }
}

async function main() {
  const listener = net.createServer()
  listener.listen(0, '127.0.0.1'); await once(listener, 'listening')
  const port = listener.address().port
  await new Promise(resolve => listener.close(resolve))
  base = `http://127.0.0.1:${port}`
  await start(port)
  const preflight = await originalFetch(base + '/transactions', { method: 'OPTIONS', headers: {
    Origin: 'http://localhost:5173', 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'content-type',
  } })
  assert.equal(preflight.status, 200)
  assert.equal(preflight.headers.get('access-control-allow-origin'), 'http://localhost:5173')
  assert.equal(preflight.headers.get('access-control-allow-credentials'), 'true')
  console.log('PASS isolated credentialed CORS preflight (not a browser privacy-policy test)')
  const bundle = buildSync({ entryPoints: [resolve('src/api.js')], bundle: true, write: false, platform: 'node', format: 'cjs',
    define: { 'import.meta.env': JSON.stringify({ VITE_API_URL: base }) } }).outputFiles[0].text
  const mod = new Module(resolve('workflow.generated.cjs'), module)
  mod.filename = resolve('workflow.generated.cjs'); mod.paths = module.paths; mod._compile(bundle, mod.filename)
  const { api } = mod.exports
  global.fetch = async (url, options) => {
    assert.ok(String(url).startsWith(base + '/'), 'Tests must remain local')
    assert.equal(options.credentials, 'include')
    const headers = { ...options.headers, Origin: 'http://localhost:5173' }
    if (cookie) headers.Cookie = cookie
    const response = await originalFetch(url, { ...options, headers })
    for (const value of response.headers.getSetCookie()) cookie = value.split(';')[0]
    return response
  }
  const credentials = { email: 'frontend_alpha@example.com', password: 'isolated-test-password-123' }
  const first = await api.signup({ ...credentials, name: 'Test Alpha', monthly_income: 1000.25 })
  assert.equal((await api.me()).id, first.id)
  assert.equal((await api.updateProfile({ name: 'Updated Alpha', monthly_income: 2000.15 })).monthly_income, 2000.15)
  const period = [first.id, 2026, 10]
  const txn = { user_id: first.id, amount: 0.1, category: 'Food', date: '2026-10-10', frequency: 'daily', source: 'manual' }
  const saved = await api.createTransaction(txn)
  await api.createTransaction({ ...txn, amount: 0.2 })
  await api.createBudget({ user_id: first.id, year: 2026, month: 10, category: 'Food', monthly_limit: 500.25 })
  const bill = await api.createBill({ user_id: first.id, year: 2026, month: 10, name: 'Test bill', category: 'Bills', amount: 10.25, due_day: 10 })
  assert.equal((await api.getPaceAll(...period))[0].spent_so_far, 0.3)
  await api.updateTransaction(saved.id, { ...txn, amount: 0.15, merchant: 'Test merchant' })
  assert.equal((await api.listTransactions(...period)).find(t => t.id === saved.id).amount, 0.15)
  assert.equal((await api.listTransactions(first.id, 2026, 9)).length, 0)
  await api.payBill(bill.id, 2026, 10)
  await api.payBill(bill.id, 2026, 10)
  assert.equal((await api.listTransactions(...period)).filter(t => t.source === 'bill').length, 1)
  await api.unpayBill(bill.id, 2026, 10)
  assert.equal((await api.listTransactions(...period)).filter(t => t.source === 'bill').length, 0)
  console.log('PASS profile, decimal money, transaction CRUD, month reads, budget and retry-safe bill actions')

  const previews = await api.ingestSms(first.id, 'Rs.450.00 debited from A/c XX1234 on 10-10-2026 to SWIGGY')
  assert.equal(previews.length, 1)
  const key = 'frontend-workflow-batch'
  await api.commitIngest(first.id, previews, key)
  await api.commitIngest(first.id, previews, key)
  assert.equal((await api.listTransactions(...period)).filter(t => t.source === 'sms').length, 1)
  const csv = new File(['Date,Description,Debit,Credit\n10-10-2026,TEST SHOP,25.50,\n10-10-2026,SALARY,,100\n'], 'test.csv', { type: 'text/csv' })
  const rows = await api.ingestStatement(csv)
  assert.equal(rows.length, 1); assert.equal(rows[0].amount, 25.5)
  console.log('PASS SMS preview, idempotent import commit, multipart CSV debit/credit parsing')

  const reply = await api.coachChat(first.id, 'Propose a test expense', 2026, 10)
  const proposal = reply.proposed_expenses[0]
  assert.ok(proposal)
  assert.equal((await api.listTransactions(...period)).filter(t => t.source === 'chat').length, 0)
  await api.resolveProposal(proposal.id, 'save'); await api.resolveProposal(proposal.id, 'save')
  assert.equal((await api.listTransactions(...period)).filter(t => t.source === 'chat').length, 1)
  const next = await api.coachChat(first.id, 'Another proposal', 2026, 10)
  await api.resolveProposal(next.proposed_expenses[0].id, 'cancel')
  assert.equal((await api.listTransactions(...period)).filter(t => t.source === 'chat').length, 1)
  console.log('PASS persisted Coco chat and explicit retry-safe Save/Cancel (AI response is a deterministic test stub)')

  const expected = (await api.listTransactions(...period)).length
  await api.logout(); cookie = ''; api.resetSession()
  await api.login(credentials)
  assert.equal((await api.listTransactions(...period)).length, expected)
  assert.equal((await api.listBudgets(...period)).length, 1)
  assert.equal((await api.listBills(...period)).length, 1)
  assert.equal((await api.getCoachHistory(first.id)).length, 4)
  await stop(); cookie = ''; api.resetSession(); await start(port)
  await api.login(credentials)
  assert.equal((await api.me()).name, 'Updated Alpha')
  assert.equal((await api.listTransactions(...period)).length, expected)
  assert.equal((await api.listBudgets(...period)).length, 1)
  assert.equal((await api.listBills(...period)).length, 1)
  assert.equal((await api.getCoachHistory(first.id)).length, 4)
  await api.createTransaction({ ...txn, amount: 1.01 })
  console.log('PASS logout/login and backend-restart persistence with a fresh cookie jar; continued transaction creation')

  const firstCookie = cookie
  cookie = ''; api.resetSession()
  const second = await api.signup({ email: 'frontend_beta@example.com', password: 'isolated-test-password-456', name: 'Test Beta', monthly_income: 0 })
  assert.deepEqual(await api.listTransactions(second.id, 2026, 10), [])
  for (const operation of [() => api.listTransactions(...period), () => api.listBudgets(...period), () => api.listBills(...period),
    () => api.getCoachHistory(first.id), () => api.updateTransaction(saved.id, txn), () => api.deleteTransaction(saved.id),
    () => api.payBill(bill.id, 2026, 10), () => api.resolveProposal(proposal.id, 'save'),
    () => api.unpayBill(bill.id, 2026, 10), () => api.deleteBill(bill.id), () => api.clearCoachHistory(first.id),
    () => api.createBudget({ user_id: first.id, year: 2026, month: 10, category: 'Food', monthly_limit: 999 }),
    () => api.createBill({ user_id: first.id, year: 2026, month: 10, category: 'Bills', name: 'Forbidden', amount: 1, due_day: 1 })]) {
    await assert.rejects(operation, error => [403, 404].includes(error.status))
  }
  cookie = firstCookie; api.resetSession()
  await api.deleteTransaction(saved.id)
  assert.ok(!(await api.listTransactions(...period)).some(t => t.id === saved.id))
  await api.logout(); cookie = firstCookie
  await assert.rejects(api.ingestStatement(csv), error => error.status === 401)
  assert.ok(events.includes('smartspend:logout'))
  console.log('PASS two-account isolation, deletion, revoked session and expired multipart-upload handling')
}
main().catch(() => { console.error('FAIL isolated frontend workflow (raw errors suppressed)'); process.exitCode = 1 })
  .finally(async () => { global.fetch = originalFetch; await stop(); assert.ok(resolve(temporary).startsWith(resolve(tmpdir()) + require('node:path').sep + 'smartspend-frontend-')); rmSync(temporary, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 }) }).catch(() => { console.error('FAIL isolated test cleanup'); process.exitCode = 1 })
