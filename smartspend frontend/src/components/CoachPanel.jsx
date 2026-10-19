import Icon from './Icon.jsx'
import { useConfirm } from './ConfirmDialog.jsx'
import React, { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'

const MAX_ERROR_LENGTH = 160

const GREETING = {
  role: 'model',
  content: "Hey! I'm Coco, your AI money coach. Ask me anything about your spending, or tap a suggestion below to get started.",
}

const STARTER_PROMPTS = [
  'How can I save more money?',
  'Am I on track this month?',
  "What's my biggest expense?",
  'Give me a 7-day savings challenge',
]

function TypingDots() {
  return (
    <div className="chat-bubble model typing" aria-label="Coco is typing">
      <span className="dot" />
      <span className="dot" />
      <span className="dot" />
    </div>
  )
}

const SpeechRecognitionAPI =
  typeof window !== 'undefined' ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null
const SPEECH_SUPPORTED = !!SpeechRecognitionAPI
const VOICE_OUTPUT_SUPPORTED = typeof window !== 'undefined' && !!window.speechSynthesis

export default function CoachPanel({ userId, year, month, onExpenseLogged, active = true }) {
  const confirm = useConfirm()
  const sending = useRef(false)
  const resolving = useRef(false)
  const [retryHistory, setRetryHistory] = useState(0)
  const [proposals, setProposals] = useState([])
  const [proposalBusy, setProposalBusy] = useState('')
  const [notice, setNotice] = useState('')

  const [messages, setMessages] = useState([GREETING])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [error, setError] = useState('')
  const [listening, setListening] = useState(false)
  const [voiceOutput, setVoiceOutput] = useState(false)
  const scrollRef = useRef(null)
  const recognitionRef = useRef(null)
  const voiceOutputRef = useRef(false)
  const transcriptRef = useRef('')

  useEffect(() => {
    voiceOutputRef.current = voiceOutput
    if (!voiceOutput && VOICE_OUTPUT_SUPPORTED) window.speechSynthesis.cancel()
  }, [voiceOutput])

  const speak = (text) => {
    if (!voiceOutputRef.current || !VOICE_OUTPUT_SUPPORTED) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.rate = 1
    utterance.pitch = 1
    utterance.onerror = () => setError('Voice playback unavailable. Read the reply in the conversation.')
    try { window.speechSynthesis.speak(utterance) } catch { setError('Voice playback unavailable. Read the reply below.') }
  }

  useEffect(() => {
    if (!SPEECH_SUPPORTED) return
    const recognition = new SpeechRecognitionAPI()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = 'en-IN'

    recognition.onresult = (event) => {
      let finalChunk = ''
      let interimChunk = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const chunk = event.results[i][0].transcript
        if (event.results[i].isFinal) finalChunk += chunk + ' '
        else interimChunk += chunk
      }
      if (finalChunk) transcriptRef.current = (transcriptRef.current + ' ' + finalChunk).trim()
      setInput((transcriptRef.current + ' ' + interimChunk).trim())
    }
    recognition.onerror = event => { transcriptRef.current = ''; setListening(false); setError(event.error === 'not-allowed' ? 'Microphone access denied. Allow microphone access in browser settings, or type your message.' : 'Speech recognition failed. Check your microphone and connection, or type your message.') }
    recognition.onend = () => {
      setListening(false)
      const finalText = transcriptRef.current.trim()
      transcriptRef.current = ''
      if (finalText) setInput(finalText)
    }

    recognitionRef.current = recognition
    return () => { recognition.onend = null; recognition.abort() }
  }, [])

  useEffect(() => {
    return () => {
      if (VOICE_OUTPUT_SUPPORTED) window.speechSynthesis.cancel()
    }
  }, [])

  useEffect(() => {
    let live = true
    setHistoryLoaded(false)
    setError('')
    Promise.all([api.getCoachHistory(userId), api.getProposals(userId)])
      .then(([past, drafts]) => {
        if (!live) return
        setMessages(past.length ? past.map(m => ({ role: m.role, content: m.content })) : [GREETING])
        setProposals(drafts)
        setHistoryLoaded(true)
      })
      .catch(err => { if (live) setError(`Could not load your saved conversation: ${err.message}`) })
    return () => { live = false }
  }, [userId, retryHistory])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, loading])

  useEffect(() => {
    if (!active) {
      transcriptRef.current = ''
      recognitionRef.current?.abort()
      setListening(false)
      setVoiceOutput(false)
      if (VOICE_OUTPUT_SUPPORTED) window.speechSynthesis.cancel()
    }
  }, [active])

  const send = async (text) => {
    const trimmed = text.trim()
    if (!trimmed || sending.current || !active || !historyLoaded) return
    sending.current = true
    transcriptRef.current = ''; recognitionRef.current?.abort(); setListening(false)

    setError('')
    setMessages((prev) => [...prev, { role: 'user', content: trimmed }])
    setInput('')
    setLoading(true)

    try {
      const res = await api.coachChat(userId, trimmed, year, month)
      const logged = res.logged_expenses || []
      setProposals(prev => [...prev, ...(res.proposed_expenses || [])])
      setMessages((prev) => [...prev, { role: 'model', content: res.reply, loggedExpenses: logged }])
      speak(res.reply)
      if (logged.length > 0 && onExpenseLogged) onExpenseLogged()
    } catch (err) {
      const message = err.message || 'Something went wrong. Please try again.'
      setInput(trimmed)
      setMessages(prev => prev.slice(0, -1))
      setError(message.length > MAX_ERROR_LENGTH ? message.slice(0, MAX_ERROR_LENGTH) + '…' : message)
    } finally {
      sending.current = false
      setLoading(false)
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    send(input)
  }

  const handleReset = async () => {
    if (sending.current || !await confirm('Delete your saved Coco conversation? Pending expense proposals stay available.')) return
    sending.current = true
    setLoading(true)
    setError('')
    try {
      await api.clearCoachHistory(userId)
      if (VOICE_OUTPUT_SUPPORTED) window.speechSynthesis.cancel()
      setMessages([GREETING])
      setNotice('Saved conversation deleted.')
    } catch (err) { setError(err.message) }
    finally { sending.current = false; setLoading(false) }
  }

  const toggleListening = () => {
    if (!SPEECH_SUPPORTED || !recognitionRef.current || loading) return
    if (listening) {
      recognitionRef.current.stop()
    } else {
      if (VOICE_OUTPUT_SUPPORTED) window.speechSynthesis.cancel()
      transcriptRef.current = ''
      setInput('')
      setListening(true)
      try { recognitionRef.current.start() } catch { setListening(false); setError('Could not start microphone. Try again or type your message.') }
    }
  }

  const handleCocoFabTap = () => {
    if (VOICE_OUTPUT_SUPPORTED) setVoiceOutput(true)
    toggleListening()
  }

  const hasChatted = messages.some((m) => m.role === 'user')

  return (
    <div className="card chat-card">
      <div className="chat-panel-heading"><span className="section-icon"><Icon name="coach" /></span><div><h2>Coco</h2><p>Your saved conversation | {new Date(year, month - 1, 1).toLocaleDateString('en-IN', { month: 'long', year: 'numeric' })}</p></div><span className="ai-badge">AI money coach</span></div>
      <p className="period-note">Your conversation is saved to your account. Coco proposes expenses for your review; only Save records spending.</p>
      {proposals.length > 0 && <section className="expense-proposals" aria-label="Expenses awaiting review"><h3>Review before saving</h3>{proposals.map(p => <div className="proposal-row" key={p.id}><div><strong>INR {Number(p.amount).toFixed(2)} | {p.category}</strong><p>{p.date}{p.merchant ? ` | ${p.merchant}` : ''}{p.note ? ` | ${p.note}` : ''}</p></div>{['save', 'cancel'].map(action => <button key={action} type="button" className={`btn ${action === 'cancel' ? 'secondary' : ''}`} disabled={!!proposalBusy} onClick={async () => {
        if (resolving.current) return
        resolving.current = true
        setProposalBusy(p.id); setError('')
        try { await api.resolveProposal(p.id, action); setProposals(prev => prev.filter(row => row.id !== p.id)); setNotice(action === 'save' ? 'Expense saved to your ledger.' : 'Proposal cancelled. No expense recorded.'); if (action === 'save') onExpenseLogged?.() }
        catch (err) { setError(err.message) } finally { resolving.current = false; setProposalBusy('') }
      }}>{proposalBusy === p.id ? 'Please wait...' : action === 'save' ? 'Save expense' : 'Cancel'}</button>)}</div>)}</section>}
      {notice && <p role="status" className="success-text">{notice}</p>}
      <div className="chat-window" role="log" aria-relevant="additions" aria-live="polite" aria-label="Conversation" ref={scrollRef}>
        {historyLoaded &&
          messages.map((m, i) => (
            <div key={i} className={`chat-bubble ${m.role}`}>
              {m.content}
              {m.loggedExpenses && m.loggedExpenses.length > 0 && (
                <div className="chat-logged-chips" style={{ marginTop: 6, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {m.loggedExpenses.map((le, j) => (
                    <span
                      key={j}
                      className="chip"
                      style={{ fontSize: 16, padding: '2px 8px', opacity: 0.85 }}
                      title={le.note || ''}
                    >
                      ✓ Logged ₹{le.amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} · {le.category}
                      {le.merchant ? ` · ${le.merchant}` : ''}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        {loading && <TypingDots />}
      </div>

      {!hasChatted && (
        <div className="chat-chips">
          {STARTER_PROMPTS.map((p) => (
            <button
              key={p}
              type="button"
              className="chip"
              onClick={() => setInput(p)}
              disabled={loading || !historyLoaded}
            >
              {p}
            </button>
          ))}
        </div>
      )}

      {!historyLoaded && !error && <p role="status">Loading saved conversation...</p>}
      {!SPEECH_SUPPORTED && <p className="period-note">Voice input is unavailable in this browser. Type your message or use a browser with speech recognition.</p>}
      <p className="period-note">Review dictated text, then press Send.</p>
      {error && <div role="alert" className="buy-result warn" style={{ marginTop: 12 }}>{error}{!historyLoaded && <button className="btn secondary" onClick={() => setRetryHistory(n => n + 1)}>Retry conversation</button>}</div>}

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 6 }}>
        {VOICE_OUTPUT_SUPPORTED && (
          <button
            type="button"
            className="btn secondary"
            style={{ padding: '4px 10px', fontSize: 16 }}
            aria-pressed={voiceOutput}
            onClick={() => setVoiceOutput((v) => !v)}
            title={voiceOutput ? 'Turn off Coco\'s voice replies' : 'Have Coco speak its replies aloud'}
          >
            <Icon name="audio" />{voiceOutput ? 'Voice on' : 'Voice off'}
          </button>
        )}
      </div>

      <form className="chat-input-row" onSubmit={handleSubmit}>
        <textarea
          rows={2}
          onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) handleSubmit(event) }}
          aria-label="Message Coco"
          maxLength={4000}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={listening ? 'Listening...' : 'Ask Coco about your budget...'}
          disabled={loading || !historyLoaded}
        />
        {SPEECH_SUPPORTED && (
          <button
            type="button"
            className={`btn secondary chat-send${listening ? ' listening' : ''}`}
            onClick={toggleListening}
            aria-pressed={listening}
            disabled={loading || !historyLoaded}
            aria-label={listening ? 'Stop listening' : 'Speak to Coco'}
            title={listening ? 'Stop listening' : 'Speak your question to Coco'}
            style={listening ? { background: 'var(--accent)', color: 'var(--on-accent)' } : undefined}
          >
            <Icon name="microphone" />{listening ? 'Stop' : 'Speak'}
          </button>
        )}
        <button className="btn chat-send" type="submit" disabled={loading || !historyLoaded || !input.trim()}>
          {loading ? '...' : 'Send'}
        </button>
        {hasChatted && (
          <button
            className="btn secondary chat-send"
            type="button"
            onClick={handleReset}
            disabled={loading || !historyLoaded}
            title="Start a new conversation"
          >
            Reset
          </button>
        )}
      </form>
      <p className="composer-hint">Enter to send | Shift + Enter for a new line <span>{input.length}/4000</span></p>

      {SPEECH_SUPPORTED && (
        <button
          type="button"
          className={`coco-fab${listening ? ' listening' : ''}`}
          onClick={handleCocoFabTap}
          disabled={loading || !historyLoaded}
          aria-label={listening ? 'Stop dictation and review' : 'Talk to Coco'}
          title={listening ? 'Tap to stop and review' : 'Tap to talk to Coco'}
        >
          <span className="coco-fab-ring" aria-hidden="true" />
          {listening ? (
            <span className="coco-fab-dot" aria-hidden="true" />
          ) : (
            <svg
              className="coco-fab-icon"
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              aria-hidden="true"
            >
              <path
                d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Z"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <path
                d="M19 11a7 7 0 0 1-14 0M12 18v3"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          )}
          <span className="coco-fab-label">{listening ? 'STOP' : 'COCO'}</span>
        </button>
      )}
    </div>
  )
}
