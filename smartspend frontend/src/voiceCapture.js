// Keep recording until the user stops; process the final result before submitting.
export function createVoiceCapture({ Recognition, onTranscript, onState, onComplete, onError }) {
  let recognition
  let active = false
  let submit = false
  let cancelled = false
  let prefix = ''
  let segment = ''
  let timer
  const transcript = () => [prefix, segment].filter(Boolean).join(' ').trim()
  const finish = () => {
    if (!submit || cancelled) return
    submit = false
    clearTimeout(timer)
    onState('idle')
    const text = transcript()
    if (text) onComplete(text)
    else onError('No speech was captured. Tap the microphone to try again, or type below.')
  }
  const cancel = () => {
    cancelled = true; active = false; submit = false
    clearTimeout(timer)
    if (recognition) {
      recognition.onend = null
      recognition.onresult = null
      recognition.onerror = null
      recognition.abort()
    }
    onState('idle')
  }
  return {
    start() {
      cancelled = false; active = true; submit = false; prefix = ''; segment = ''
      recognition = new Recognition()
      recognition.continuous = true
      recognition.interimResults = true
      recognition.lang = 'en-IN'
      recognition.onresult = event => {
        if (cancelled) return
        // Results include earlier segments: rebuilding avoids duplicated interim words.
        segment = Array.from(event.results, result => result[0].transcript).join(' ').trim()
        const text = transcript()
        onTranscript(text)
        if (text.length > 4000) {
          cancel()
          onError('That message is too long. Shorten it to 4,000 characters before sending.')
        }
      }
      recognition.onerror = event => {
        if (cancelled || (event.error === 'no-speech' && active)) return
        cancel()
        onError(event.error === 'not-allowed' || event.error === 'service-not-allowed'
          ? 'Allow microphone access in your browser, or type your expense below.'
          : 'Voice input was interrupted. Your captured text is below; edit it and press Send.')
      }
      recognition.onend = () => {
        if (cancelled) return
        if (submit) { finish(); return }
        if (active) {
          prefix = transcript(); segment = ''
          timer = setTimeout(() => {
            if (!active || cancelled) return
            try { recognition.start() } catch { cancel(); onError('Voice input paused. Send the captured text below, or try again.') }
          }, 150)
        }
      }
      onState('listening')
      try { recognition.start() } catch { cancel(); onError('Could not start the microphone. Try again or type below.') }
    },
    stop() {
      if (!active || cancelled) return
      active = false; submit = true
      clearTimeout(timer)
      onState('stopping')
      // Some browsers omit end after stop. Submit the latest capture once only.
      timer = setTimeout(() => { finish(); recognition.abort() }, 5000)
      try { recognition.stop() } catch { finish() }
    },
    cancel,
  }
}
