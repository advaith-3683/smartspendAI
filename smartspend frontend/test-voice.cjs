const assert = require('node:assert/strict')
const { buildSync } = require('esbuild')
const Module = require('node:module')
const { resolve } = require('node:path')
const bundle = buildSync({ entryPoints: [resolve('src/voiceCapture.js')], bundle: true, write: false, platform: 'node', format: 'cjs' }).outputFiles[0].text
const mod = new Module(resolve('voice.generated.cjs'), module)
mod.filename = resolve('voice.generated.cjs'); mod.paths = module.paths
mod._compile(bundle, mod.filename)
const { createVoiceCapture } = mod.exports

function fixture() {
  let mic
  class Recognition {
    constructor() { mic = this; this.starts = 0 }
    start() { this.starts++ }
    stop() { this.stopped = true }
    abort() { this.aborted = true }
    result(...segments) { this.onresult?.({ results: segments.map(transcript => [{ transcript }]) }) }
    end() { this.onend?.() }
  }
  const sent = [], errors = [], states = [], transcripts = []
  const capture = createVoiceCapture({ Recognition, onComplete: text => sent.push(text),
    onState: state => states.push(state), onTranscript: text => transcripts.push(text), onError: error => errors.push(error) })
  capture.start()
  return { capture, mic, sent, errors, states, transcripts }
}

async function run() {
  const f = fixture()
  f.mic.result('I spent 200')
  f.mic.result('I spent 200 rupees', 'on lunch')
  assert.deepEqual(f.sent, [])
  f.capture.stop()
  assert.equal(f.mic.stopped, true)
  assert.deepEqual(f.sent, [], 'wait for final recognition results')
  f.mic.result('I spent 200 rupees', 'on lunch today')
  f.mic.end(); f.mic.end()
  assert.deepEqual(f.sent, ['I spent 200 rupees on lunch today'])
  assert.equal(f.states.at(-1), 'idle')
  f.capture.cancel()
  console.log('PASS tap-stop waits for final words, no duplicated interim text or double-send')

  const pause = fixture()
  pause.mic.result('I spent 50 on coffee'); pause.mic.end()
  await new Promise(resolve => setTimeout(resolve, 180))
  assert.equal(pause.mic.starts, 2)
  assert.deepEqual(pause.sent, [], 'a speech pause does not send')
  pause.mic.result('and 200 on lunch'); pause.capture.stop(); pause.mic.end()
  assert.deepEqual(pause.sent, ['I spent 50 on coffee and 200 on lunch'])
  pause.capture.cancel()
  console.log('PASS mobile recognition restart preserves all earlier speech until user stops')

  const cancelled = fixture()
  cancelled.mic.result('I spent 100'); cancelled.capture.cancel(); cancelled.mic.end()
  assert.deepEqual(cancelled.sent, [])
  assert.equal(cancelled.mic.aborted, true)
  const denied = fixture()
  denied.mic.onerror({ error: 'not-allowed' }); denied.mic.end()
  assert.deepEqual(denied.sent, [])
  assert.match(denied.errors[0], /Allow microphone/)
  const empty = fixture()
  empty.capture.stop(); empty.mic.end(); empty.capture.cancel()
  assert.deepEqual(empty.sent, [])
  assert.match(empty.errors[0], /No speech/)
  console.log('PASS navigation cancellation, permission denial and empty speech never submit')
}
run().catch(error => { console.error(error); process.exitCode = 1 })
