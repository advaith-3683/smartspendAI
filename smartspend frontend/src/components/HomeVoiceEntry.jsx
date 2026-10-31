import React, { useEffect, useRef, useState } from 'react'
import Icon from './Icon.jsx'
import { api } from '../api.js'
import { createVoiceCapture } from '../voiceCapture.js'
import { formatMoney } from '../money.js'

export default function HomeVoiceEntry({ userId, year, month, onSaved, reviewFirst = false }) {
  const [phase, setPhase] = useState('idle')
  const [text, setText] = useState('')
  const [reply, setReply] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [proposals, setProposals] = useState([])
  const [autoSave, setAutoSave] = useState(!reviewFirst)
  const [resolving, setResolving] = useState(false)
  const [proposalRetry, setProposalRetry] = useState(0)
  const [proposalLoadError, setProposalLoadError] = useState('')
  const [loadingProposals, setLoadingProposals] = useState(false)
  const capture = useRef(null)
  const busy = useRef(false)
  const live = useRef(true)
  const sendRef = useRef(null)
  const proposalVersion = useRef(0)
  const Recognition = typeof window === 'undefined' ? null : window.SpeechRecognition || window.webkitSpeechRecognition

  useEffect(() => {
    live.current = true
    const cancelHidden = () => { if (document.hidden) capture.current?.cancel() }
    document.addEventListener('visibilitychange', cancelHidden)
    return () => {
      live.current = false
      capture.current?.cancel()
      document.removeEventListener('visibilitychange', cancelHidden)
    }
  }, [userId])

  useEffect(() => {
    let active = true
    const version = proposalVersion.current
    setProposalLoadError(''); setLoadingProposals(true)
    api.getProposals(userId).then(rows => {
      if (active && live.current && proposalVersion.current === version) setProposals(rows)
    }).catch(err => {
      if (active && live.current && proposalVersion.current === version) {
        setProposalLoadError(`Could not load saved expense proposals. ${err?.message || 'Please try again.'}`)
      }
    }).finally(() => {
      if (active && live.current) setLoadingProposals(false)
    })
    return () => { active = false }
  }, [userId, proposalRetry])

  const resolve = async (proposal, action) => {
    proposalVersion.current += 1
    await api.resolveProposal(proposal.id, action)
    if (action === 'save') onSaved?.()
    if (!live.current) return
    setProposals(previous => previous.filter(row => row.id !== proposal.id))
  }

  const send = async message => {
    const content = message.trim()
    if (!live.current || busy.current || !content || content.length > 4000) return
    busy.current = true
    proposalVersion.current += 1
    capture.current?.cancel()
    setPhase('sending'); setText(content); setError(''); setNotice(''); setReply('')
    try {
      const result = await api.coachChat(userId, content, year, month)
      if (!live.current) return
      setReply(result.reply)
      const drafts = result.proposed_expenses || []
      setProposals(previous => [...previous, ...drafts])
      let saved = 0
      if (autoSave) {
        for (const draft of drafts) {
          if (!live.current) break
          await resolve(draft, 'save')
          saved += 1
          if (live.current) setNotice(`${saved} ${saved === 1 ? 'expense' : 'expenses'} saved to your ledger.`)
        }
      }
      if (live.current) setText('')
    } catch (err) {
      if (live.current) setError(`${err.message} Any expenses awaiting review are shown below. Check your ledger before resending.`)
    } finally {
      busy.current = false
      if (live.current) setPhase('idle')
    }
  }
  sendRef.current = send

  const toggle = () => {
    if (phase === 'listening') { capture.current?.stop(); return }
    if (busy.current || !Recognition || phase !== 'idle') return
    setError(''); setNotice(''); setText('')
    capture.current = createVoiceCapture({ Recognition,
      onTranscript: value => { if (live.current) setText(value) },
      onState: value => { if (live.current) setPhase(value) },
      onComplete: value => sendRef.current(value),
      onError: value => { if (live.current) setError(value) },
    })
    capture.current.start()
  }
  const locked = phase !== 'idle' || resolving
  return <section className="card home-voice" aria-label="Talk to Coco from Home">
    <div className="home-voice-intro"><span className="ai-badge">COCO · VOICE EXPENSES</span><h2>Say it. Let Coco handle it.</h2><p>Tap the microphone, tell Coco what you spent, then tap again to stop and send your complete message.</p></div>
    <button className={`voice-toggle ${phase === 'listening' ? 'is-listening' : ''}`} type="button" onClick={toggle}
      disabled={!Recognition || phase === 'stopping' || phase === 'sending' || resolving}
      aria-pressed={phase === 'listening'} aria-label={phase === 'listening' ? 'Stop recording and send to Coco' : 'Start recording for Coco'}>
      {phase === 'sending' || phase === 'stopping' ? <span className="spinner" /> : <Icon name={phase === 'listening' ? 'close' : 'microphone'} />}
      <span>{phase === 'listening' ? 'Stop & send' : phase === 'stopping' ? 'Finishing your message…' : phase === 'sending' ? 'Coco is working…' : 'Tap to speak'}</span>
    </button>
    <p className="voice-status" role="status">{phase === 'listening' ? 'Microphone on. Tap Stop & send when you finish.' : !Recognition ? 'Voice recognition is unavailable in this browser. Type below or use your keyboard’s microphone.' : 'Microphone off. You can also type your message below.'}</p>
    <label className="voice-auto-save"><input type="checkbox" checked={autoSave} disabled={locked} onChange={event => setAutoSave(event.target.checked)} /><span>Save detected expenses automatically after sending</span></label>
    <p className="period-note">{autoSave ? 'Stopping sends your message and saves the expenses Coco extracts. Review your ledger afterward.' : 'Coco will show detected expenses below for you to review and save.'}</p>
    <form className="voice-composer" onSubmit={event => { event.preventDefault(); send(text) }}>
      <label htmlFor="home-coco-message">Your message to Coco</label>
      <textarea id="home-coco-message" rows={3} value={text} maxLength={4000} disabled={locked} onChange={event => setText(event.target.value)} placeholder="For example: I spent 200 rupees on lunch today." />
      <button className="btn secondary" disabled={locked || !text.trim() || text.length > 4000}>Send to Coco <Icon name="right" /></button>
    </form>
    {error && <p className="error-text" role="alert">{error}</p>}
    {notice && <p className="success-text" role="status">{notice}</p>}
    {reply && <div className="home-voice-reply" role="status"><strong>Coco</strong><p>{reply}</p></div>}
    {loadingProposals && <p className="period-note" role="status">Loading saved expense proposals...</p>}
    {proposalLoadError && <div className="error-text" role="alert"><p>{proposalLoadError}</p><button className="btn secondary" type="button" disabled={loadingProposals || locked} onClick={() => setProposalRetry(previous => previous + 1)}>Retry saved proposals</button></div>}
    {proposals.length > 0 && <section className="expense-proposals" aria-label="Home expenses awaiting review"><h3>Expenses awaiting review</h3>{proposals.map(proposal => <div className="proposal-row" key={proposal.id}><div><strong>INR {formatMoney(proposal.amount)} · {proposal.category}</strong><p>{proposal.date} {proposal.merchant}</p></div>{['save', 'cancel'].map(action => <button className={`btn ${action === 'cancel' ? 'secondary' : ''}`} type="button" key={action} disabled={locked} onClick={async () => {
      if (busy.current) return
      busy.current = true; setResolving(true); setError('')
      try { await resolve(proposal, action); if (live.current) setNotice(action === 'save' ? 'Expense saved to your ledger.' : 'Expense proposal cancelled.') }
      catch (err) { if (live.current) setError(err.message) }
      finally { busy.current = false; if (live.current) setResolving(false) }
    }}>{action === 'save' ? 'Save expense' : 'Cancel'}</button>)}</div>)}</section>}
  </section>
}
