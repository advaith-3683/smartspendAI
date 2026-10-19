const { buildSync } = require('esbuild')
const { resolve } = require('node:path')
const Module = require('node:module')
const assert = require('node:assert/strict')
const bundle = buildSync({ entryPoints: [resolve('src/api.js')], bundle: true, write: false, platform: 'node', format: 'cjs', define: { 'import.meta.env': '{}' } }).outputFiles[0].text
const mod = new Module(resolve('api-test.generated.cjs'), module)
mod.filename = resolve('api-test.generated.cjs')
mod.paths = module.paths
mod._compile(bundle, mod.filename)
const { api } = mod.exports

async function main() {
  const originalFetch = global.fetch
  const originalWindow = global.window
  const events = []
  global.window = { dispatchEvent: event => events.push(event.type) }
  try {
    global.fetch = async (url, options) => {
      assert.equal(options.credentials, 'include')
      assert.equal(options.headers['Content-Type'], undefined)
      assert.ok(options.signal instanceof AbortSignal)
      return new Response(JSON.stringify({ id: 1 }), { status: 200 })
    }
    assert.deepEqual(await api.me(), { id: 1 })
    console.log('PASS credentialed session GET without unnecessary preflight headers')
    global.fetch = async (url, options) => {
      assert.equal(options.headers['Content-Type'], 'application/json'); assert.equal(options.credentials, 'include')
      return new Response('{}')
    }
    await api.login({ email: 'test@example.com', password: 'test-password' })
    console.log('PASS credentialed JSON login request')

    global.fetch = async (url) => {
      assert.equal(url, 'https://smartspend-backend-lsk5.onrender.com/auth/me')
      return new Response('{}')
    }
    await api.me()
    console.log('PASS production default uses live HTTPS API, never localhost')

    global.fetch = async (url, options) => {
      assert.ok(options.body instanceof FormData)
      assert.equal(options.headers['Content-Type'], undefined)
      assert.equal(options.credentials, 'include')
      return new Response(JSON.stringify({ detail: 'Please log in' }), { status: 401 })
    }
    await assert.rejects(api.ingestStatement(new File(['test'], 'statement.csv')), /Please log in/)
    assert.deepEqual(events, ['smartspend:logout'])
    console.log('PASS expired upload session resets authentication')

    global.fetch = async () => new Response(JSON.stringify({ detail: [{ msg: 'Invalid amount' }, { msg: 'Invalid date' }] }), { status: 422 })
    await assert.rejects(api.createTransaction({}), /Invalid amount; Invalid date/)
    console.log('PASS readable validation errors')

    global.fetch = async () => { throw new TypeError('Failed to fetch') }
    await assert.rejects(api.me(), error => error.code === 'network' && error.message === 'Cannot connect to SmartSpend. Retry shortly. If it continues, report the site address to support.')
    console.log('PASS actionable network errors')

    events.length = 0
    global.fetch = async () => new Response(JSON.stringify({ detail: 'Invalid username or password' }), { status: 401 })
    await assert.rejects(api.login({ email: 'test@example.com', password: 'not-a-secret' }), error => error.status === 401)
    assert.deepEqual(events, [])
    console.log('PASS failed login preserves form without a session-expiry event')

    let finish
    global.fetch = () => new Promise(resolve => { finish = resolve })
    const old = api.me()
    api.resetSession()
    finish(new Response('{"id":99}'))
    await assert.rejects(old, /Account changed/)
    console.log('PASS stale account response cannot restore old private data')

    let finishError
    global.fetch = async () => ({ ok: false, status: 401, json: () => new Promise(resolve => { finishError = resolve }) })
    const staleError = api.me()
    await Promise.resolve()
    api.resetSession()
    finishError({ detail: 'Please log in' })
    await assert.rejects(staleError, /Account changed/)
    assert.deepEqual(events, [])
    console.log('PASS delayed old-session 401 cannot log out a newer account')

    global.fetch = async () => new Response(null, { status: 204 })
    assert.equal(await api.logout(), null)
    console.log('PASS successful empty response')

    global.fetch = async () => new Response(JSON.stringify({ detail: 'AI service unavailable. Try again later.' }), { status: 503 })
    await assert.rejects(api.coachChat(1, 'test', 2026, 10), error => error.status === 503 && /unavailable/.test(error.message))
    global.fetch = async () => new Response('<html>unavailable</html>')
    await assert.rejects(api.me(), /Unexpected server response/)
    console.log('PASS API failures and invalid JSON never produce success data')

    const originalTimeout = global.setTimeout
    try {
      global.setTimeout = callback => { queueMicrotask(callback); return 0 }
      global.fetch = (_, options) => new Promise((_, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))))
      await assert.rejects(api.createTransaction({}), /too long.*Check your ledger/)
      console.log('PASS save timeout warns to inspect records before retrying')
    } finally { global.setTimeout = originalTimeout }
  } finally {
    global.fetch = originalFetch
    global.window = originalWindow
  }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
