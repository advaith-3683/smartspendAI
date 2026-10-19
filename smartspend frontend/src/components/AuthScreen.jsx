import React, { useRef, useState } from 'react'
import { api } from '../api.js'
import Icon from './Icon.jsx'
import { Brand, Introduction, FinanceMotif } from './design/Identity.jsx'
import { Notice } from './design/Notice.jsx'
import './AuthScreen.css'

export function ConnectionAlert({ message, onRetry, busy = false }) {
  if (!message) return null
  return <Notice className="connection-alert" title="Connection unavailable" action={<button type="button" className="text-button" disabled={busy} onClick={onRetry}><Icon name="refresh" />{busy ? 'Trying again...' : 'Retry'}</button>}><p>{message}</p></Notice>
}

export default function AuthScreen({ onCreated, sessionError, onRetrySession, retryingSession }) {
  const locked = useRef(false)
  const formRef = useRef(null)
  const [signup, setSignup] = useState(false)
  const [name, setName] = useState('')
  const [income, setIncome] = useState('0')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [visible, setVisible] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [legacy, setLegacy] = useState(false)
  async function submit(event) {
    event.preventDefault()
    if (locked.current) return
    locked.current = true; setError(''); setLoading(true)
    try {
      const credentials = legacy && !signup ? { username: email.trim(), password } : { email: email.trim(), password }
      if (signup) await api.signup({ ...credentials, name: name.trim(), monthly_income: Number(income) })
      else if (legacy) await api.legacyLogin(credentials)
      else await api.login(credentials)
      let user
      try { user = await api.me() } catch (err) {
        if (err.status === 401) throw new Error('Sign-in was accepted, but the session could not be restored. Retry sign-in. If this repeats, report the session error to support.')
        throw err
      }
      onCreated(user)
    } catch (err) { setError(err.message) }
    finally { locked.current = false; setLoading(false) }
  }
  return <main className="auth-page"><header className="auth-masthead"><Brand /></header><div className="auth-grid">
    <aside className="intro-column" aria-label="About SmartSpend"><Introduction heading="h2" /><FinanceMotif /></aside>
    <section className="auth-form-panel" aria-labelledby="auth-title"><div className="auth-form-wrap"><div className="auth-form-heading"><span className="form-kicker">Your personal workspace</span><h1 id="auth-title">{signup ? 'Create your account' : 'Welcome back'}</h1><p>{signup ? 'Start building a clearer picture of your finances.' : 'Sign in to your SmartSpend account.'}</p></div>
      <ConnectionAlert message={sessionError} onRetry={onRetrySession} busy={retryingSession} />
      <form ref={formRef} onSubmit={submit} aria-busy={loading}>
        {signup && <div className="field"><label htmlFor="name">Your name</label><input id="name" required maxLength={100} autoComplete="name" value={name} onChange={e => setName(e.target.value)} /></div>}
        <div className="field"><label htmlFor="email">{legacy && !signup ? 'Legacy account ID' : 'Email'}</label><input id="email" type={legacy && !signup ? 'text' : 'email'} required maxLength={legacy && !signup ? 100 : 254} autoComplete={legacy && !signup ? 'username' : 'email'} aria-describedby={error ? 'auth-error' : undefined} autoCapitalize="none" spellCheck={false} value={email} onChange={e => setEmail(e.target.value)} /></div>
        <div className="field"><label htmlFor="password">Password</label><div className="password-field"><input id="password" type={visible ? 'text' : 'password'} required minLength={signup ? 12 : undefined} maxLength={128} autoComplete={signup ? 'new-password' : 'current-password'} aria-describedby={[signup && 'password-help', error && 'auth-error'].filter(Boolean).join(' ') || undefined} value={password} onChange={e => setPassword(e.target.value)} /><button type="button" className="password-toggle" aria-label={visible ? 'Hide password' : 'Show password'} aria-pressed={visible} onClick={() => setVisible(value => !value)}><Icon name="eye" />{visible ? 'Hide' : 'Show'}</button></div>{signup && <small id="password-help" className="field-hint">Use 12–128 characters. Choose a password you don’t use elsewhere.</small>}</div>
        {signup && <div className="field"><label htmlFor="income">Monthly income (optional) <span className="label-note">INR</span></label><input id="income" type="number" min="0" max="1000000000" step="0.01" inputMode="decimal" value={income} onChange={e => setIncome(e.target.value)} /><small className="field-hint">You can update this later.</small></div>}
        {error && <div className="form-alert" role="alert" id="auth-error"><Icon name="alert" /><div><p>{error}</p><button type="button" className="text-button" disabled={loading} onClick={() => formRef.current?.requestSubmit()}>Try again</button></div></div>}
        <button className="btn auth-submit" type="submit" disabled={loading || retryingSession}>{loading ? <><span className="spinner" />{signup ? 'Creating your account…' : 'Signing in…'}</> : signup ? 'Create account' : 'Sign in'}</button>
      </form>
      <p className="auth-switch">{signup ? 'Already have an account?' : 'New to SmartSpend?'} <button type="button" className="text-button" disabled={loading} onClick={() => { setSignup(value => !value); setLegacy(false); setEmail(''); setPassword(''); setVisible(false); setError('') }}>{signup ? 'Sign in' : 'Create an account'}</button></p>
      {!signup && <p className="auth-switch"><button type="button" className="text-button" disabled={loading} onClick={() => { setLegacy(value => !value); setEmail(''); setPassword(''); setError('') }}>{legacy ? 'Use email sign-in' : 'Sign in to an older account'}</button></p>}
      {legacy && !signup && <p className="field-hint">Use your existing account ID, then add an email in Account. Your saved records stay with that account.</p>}
    </div></section>
  </div></main>
}
