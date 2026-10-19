import React, { useRef, useState } from 'react'
import { api } from '../api.js'

export default function EmailEnrollment({ user, onSaved }) {
  const busy = useRef(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  if (user.email) return <section className="card"><h2>Sign-in email</h2><p>{user.email}</p><p className="period-note">Use this email to sign in. Its format is valid; ownership has not been verified. Adding an email does not combine accounts.</p></section>
  return <section className="card profile-editor"><h2>Add your sign-in email</h2><p className="period-note">Confirm your current password to keep this account and all its saved records. Once added, use email sign-in.</p>
    <form onSubmit={async event => {
      event.preventDefault(); if (busy.current) return
      busy.current = true; setSaving(true); setError('')
      try { const next = await api.enrollEmail({ email: email.trim(), current_password: password }); setPassword(''); onSaved(next) }
      catch (err) { setError(err.message) }
      finally { busy.current = false; setSaving(false) }
    }}>
      <label>Email<input type="email" autoComplete="email" autoCapitalize="none" spellCheck={false} required maxLength={254} value={email} onChange={event => setEmail(event.target.value)} /></label>
      <label>Current password<input type="password" autoComplete="current-password" required minLength={12} maxLength={128} value={password} onChange={event => setPassword(event.target.value)} /></label>
      {error && <p role="alert" className="error-text">{error}</p>}
      <button className="btn" disabled={saving}>{saving ? 'Adding email...' : 'Add sign-in email'}</button>
    </form>
  </section>
}
