import React from 'react'

// Shared with the approved full-screen Design A; no API or preview-only state.
function Mark() {
  return <svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" aria-hidden="true"><path d="M4 7V4h14v3M3 7h18v14H3zM15 12h6v5h-6z" /><path d="M18 14.5h.01" strokeLinecap="round" /></svg>
}
export function Arrow() {
  return <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 12h15m-5-5 5 5-5 5" /></svg>
}


export function Brand() {
  return <div className="brand"><span className="brand-symbol"><Mark /></span><span>SmartSpend<span className="ai-label">AI</span></span></div>
}
export function Introduction({ heading: Heading = 'h1' }) {
  return <div className="introduction"><span className="eyebrow">A clearer everyday</span><Heading>Your money.<br /><span>Your next move.</span></Heading><p>Track your spending, plan with purpose, and find a little clarity with Coco.</p></div>
}
export function FinanceMotif() {
  return <div className="finance-motif" aria-hidden="true"><div><span>01</span><strong>Everyday spending</strong><Arrow /></div><div><span>02</span><strong>Thoughtful budgets</strong><Arrow /></div><div><span>03</span><strong>A little help from Coco</strong><Arrow /></div></div>
}
