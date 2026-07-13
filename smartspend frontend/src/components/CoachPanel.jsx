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

export default function CoachPanel({ userId, year, month }) {
  const [messages, setMessages] = useState([GREETING])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [error, setError] = useState('')
  const [listening, setListening] = useState(false)
  const [voiceOutput, setVoiceOutput] = useState(false)
  const scrollRef = useRef(null)
  const recognitionRef = useRef(null)
  const sendRef = useRef(() => {})
  const voiceOutputRef = useRef(false)

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
    window.speechSynthesis.speak(utterance)
  }

  useEffect(() => {
    if (!SPEECH_SUPPORTED) return
    const recognition = new SpeechRecognitionAPI()
    recognition.continuous = false
    recognition.interimResults = false
    recognition.lang = 'en-IN'

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript
      sendRef.current(transcript)
    }
    recognition.onerror = () => setListening(false)
    recognition.onend = () => setListening(false)

    recognitionRef.current = recognition
    return () => recognition.stop()
  }, [])

  useEffect(() => {
    return () => {
      if (VOICE_OUTPUT_SUPPORTED) window.speechSynthesis.cancel()
    }
  }, [])

  useEffect(() => {
    api
      .getCoachHistory(userId)
      .then((past) => {
        if (past.length > 0) {
          setMessages(past.map((m) => ({ role: m.role, content: m.content })))
        }
      })
      .catch(() => {}) // non-critical, fall back to fresh greeting
      .finally(() => setHistoryLoaded(true))
  }, [userId])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, loading])

  const send = async (text) => {
    const trimmed = text.trim()
    if (!trimmed || loading) return

    setError('')
    setMessages((prev) => [...prev, { role: 'user', content: trimmed }])
    setInput('')
    setLoading(true)

    try {
      const res = await api.coachChat(userId, trimmed, year, month)
      setMessages((prev) => [...prev, { role: 'model', content: res.reply }])
      speak(res.reply)
    } catch (err) {
      const message = err.message || 'Something went wrong. Please try again.'
      setError(message.length > MAX_ERROR_LENGTH ? message.slice(0, MAX_ERROR_LENGTH) + '…' : message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    sendRef.current = send
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    send(input)
  }

  const handleReset = async () => {
    if (loading) return
    try {
      await api.clearCoachHistory(userId)
    } catch (err) {
      // non-critical — clear locally regardless
    }
    if (VOICE_OUTPUT_SUPPORTED) window.speechSynthesis.cancel()
    setMessages([GREETING])
    setError('')
  }

  const toggleListening = () => {
    if (!SPEECH_SUPPORTED || !recognitionRef.current || loading) return
    if (listening) {
      recognitionRef.current.stop()
      setListening(false)
    } else {
      if (VOICE_OUTPUT_SUPPORTED) window.speechSynthesis.cancel()
      setListening(true)
      recognitionRef.current.start()
    }
  }

  const hasChatted = messages.some((m) => m.role === 'user')

  return (
    <div className="card chat-card">
      <div className="chat-window" ref={scrollRef}>
        {historyLoaded &&
          messages.map((m, i) => (
            <div key={i} className={`chat-bubble ${m.role}`}>
              {m.content}
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
              onClick={() => send(p)}
              disabled={loading}
            >
              {p}
            </button>
          ))}
        </div>
      )}

      {error && <div className="buy-result warn" style={{ marginTop: 12 }}>{error}</div>}

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 6 }}>
        {VOICE_OUTPUT_SUPPORTED && (
          <button
            type="button"
            className="btn secondary"
            style={{ padding: '4px 10px', fontSize: 11 }}
            onClick={() => setVoiceOutput((v) => !v)}
            title={voiceOutput ? 'Turn off Coco\'s voice replies' : 'Have Coco speak its replies aloud'}
          >
            {voiceOutput ? '🔊 Voice on' : '🔈 Voice off'}
          </button>
        )}
      </div>

      <form className="chat-input-row" onSubmit={handleSubmit}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={listening ? 'Listening...' : 'Ask Coco about your budget...'}
          disabled={loading}
        />
        {SPEECH_SUPPORTED && (
          <button
            type="button"
            className={`btn secondary chat-send${listening ? ' listening' : ''}`}
            onClick={toggleListening}
            disabled={loading}
            title={listening ? 'Stop listening' : 'Speak your question to Coco'}
            style={listening ? { background: 'var(--gold, #d4af37)', color: '#111' } : undefined}
          >
            {listening ? '● Stop' : '🎤'}
          </button>
        )}
        <button className="btn chat-send" type="submit" disabled={loading || !input.trim()}>
          {loading ? '...' : 'Send'}
        </button>
        {hasChatted && (
          <button
            className="btn secondary chat-send"
            type="button"
            onClick={handleReset}
            disabled={loading}
            title="Start a new conversation"
          >
            Reset
          </button>
        )}
      </form>
    </div>
  )
}
