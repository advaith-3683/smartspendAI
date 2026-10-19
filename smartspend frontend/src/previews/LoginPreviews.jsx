import React, { useState } from 'react'
import './previews.css'

import { Arrow, Brand, Introduction, FinanceMotif } from '../components/design/Identity.jsx'

const designs = { a: ['Graphite & lime', 'Bold, compact, everyday finance.'], b: ['White & violet', 'Crisp, expressive, a little unexpected.'], c: ['Charcoal & warm gold', 'Quiet confidence. A considered finish.'] }

function LoginForm() {
  const [visible, setVisible] = useState(false)
  const [notice, setNotice] = useState('')
  return <section className="login-section" aria-labelledby="login-title"><div className="form-heading"><span className="form-kicker">Your personal workspace</span><h2 id="login-title">Welcome back</h2><p>Sign in to your SmartSpend account.</p></div>
    {/* No form element, input names, editable credentials, API imports or network calls. */}
    <div className="preview-form" role="form" aria-label="Non-submitting login preview">
      <label htmlFor="preview-username">Username<input id="preview-username" value="preview_user" readOnly autoComplete="off" spellCheck={false} aria-describedby="preview-note" /></label>
      <label htmlFor="preview-password">Password<span className="password-wrap"><input id="preview-password" type={visible ? 'text' : 'password'} value="preview-only" readOnly autoComplete="off" aria-describedby="preview-note" /><button type="button" className="visibility" aria-label={visible ? 'Hide password' : 'Show password'} aria-pressed={visible} onClick={() => setVisible(value => !value)}>{visible ? 'Hide' : 'Show'}</button></span></label>
      <button type="button" className="submit" onClick={() => setNotice('Preview only. No sign-in request was sent.')}><span>Sign in</span><Arrow /></button>
    </div>
    <p className="signup-prompt">New to SmartSpend? <button type="button" onClick={() => setNotice('Account creation is disabled in this design preview.')}>Create an account</button></p>
    <p id="preview-note" className="preview-note">Design preview · Demo fields are read-only. No credentials are submitted.</p>
    {notice && <p className="preview-feedback" role="status">{notice}</p>}
  </section>
}

export default function LoginPreviews({ variant }) {
  const selected = designs[variant] ? variant : 'a'
  return <div className={`preview-root design-${selected}`}><a className="skip" href="#design">Skip to design</a><header className="comparison-bar"><div><strong>LOGIN EXPLORATIONS</strong><span>Isolated preview · Working app unchanged</span></div><nav aria-label="Compare login designs">{Object.entries(designs).map(([key, [name]]) => <a key={key} href={`/design-preview/${key}/`} aria-current={selected === key ? 'page' : undefined}><b>{key.toUpperCase()}</b><span>{name}</span></a>)}</nav></header>
    <main id="design" tabIndex={-1} className="design-stage" aria-label={`Option ${selected.toUpperCase()}: ${designs[selected][0]}`}>
      {selected === 'a' && <div className="graphite-frame"><div className="design-masthead"><Brand /><span className="masthead-label">A / GRAPHITE & LIME</span></div><div className="graphite-grid"><div className="intro-column"><Introduction /><FinanceMotif /></div><LoginForm /></div></div>}
      {selected === 'b' && <div className="violet-frame"><div className="design-masthead"><Brand /><span className="masthead-label">B / WHITE & VIOLET</span></div><div className="violet-grid"><LoginForm /><div className="violet-editorial"><Introduction /><FinanceMotif /></div></div></div>}
      {selected === 'c' && <div className="gold-frame"><div className="gold-brand"><Brand /><span className="masthead-label">C / CHARCOAL & WARM GOLD</span></div><div className="gold-grid"><Introduction /><div className="gold-form-frame"><LoginForm /></div></div><p className="gold-signature">SPENDING <span>·</span> BUDGETS <span>·</span> COCO</p></div>}
    </main><footer className="comparison-footer">{designs[selected][1]} <span>Choose a direction before it is applied to the app.</span></footer>
  </div>
}
