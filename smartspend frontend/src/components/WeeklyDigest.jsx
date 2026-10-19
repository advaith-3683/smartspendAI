import React, { useState, useRef } from 'react'
import { api } from '../api.js'

export default function WeeklyDigest({ userId }) {
  const busy = useRef(false)
  const [digest, setDigest] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const generate = async () => {
    if (busy.current) return
    busy.current = true
    setLoading(true)
    setError('')
    try {
      const res = await api.getWeeklyDigest(userId)
      setDigest(res)
    } catch (err) {
      setError(err.message || 'Could not generate the digest right now.')
    } finally {
      busy.current = false
      setLoading(false)
    }
  }

  const change = digest ? digest.total_this_week - digest.total_last_week : 0
  const changePct = digest && digest.total_last_week > 0
    ? (change / digest.total_last_week) * 100
    : null

  return (
    <div>
      <button className="btn" type="button" onClick={generate} disabled={loading}>
        {loading ? 'Coco is reviewing your week...' : digest ? 'Refresh this week\'s check-in' : 'Generate weekly check-in'}
      </button>

      {error && <div role="alert" className="error-text" style={{ marginTop: 12 }}>{error}</div>}

      {digest && (
        <div className="card" style={{ marginTop: 16 }}>
          <div style={{ fontSize: 14, letterSpacing: '0.06em', color: 'var(--ink-faint)', fontFamily: 'var(--font-body)', marginBottom: 8 }}>
            Non-monthly spending only (recurring monthly payments excluded).<br />{digest.period_start} — {digest.period_end}
          </div>

          <div className="buy-result ok" style={{ marginBottom: 20 }}>
            {digest.digest_text}
          </div>

          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 16 }}>
            <div>
              <div style={{ fontSize: 14, color: 'var(--ink-faint)' }}>THIS WEEK</div>
              <div style={{ fontSize: 20, fontFamily: 'var(--font-body)' }}>₹{digest.total_this_week.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
            </div>
            <div>
              <div style={{ fontSize: 14, color: 'var(--ink-faint)' }}>LAST WEEK</div>
              <div style={{ fontSize: 20, fontFamily: 'var(--font-body)', color: 'var(--ink-soft)' }}>₹{digest.total_last_week.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
            </div>
            <div>
              <div style={{ fontSize: 14, color: 'var(--ink-faint)' }}>CHANGE</div>
              <div style={{ fontSize: 20, fontFamily: 'var(--font-body)', color: change > 0 ? 'var(--status-bad)' : 'var(--status-good)' }}>
                {changePct === null ? 'N/A (last week was zero)' : `${changePct >= 0 ? '+' : ''}${changePct.toFixed(0)}%`}
              </div>
            </div>
          </div>

          {digest.top_categories.length > 0 && (
            <div style={{ marginBottom: digest.bills_due_soon.length > 0 ? 12 : 0 }}>
              <div style={{ fontSize: 14, color: 'var(--ink-faint)', marginBottom: 6 }}>TOP CATEGORIES THIS WEEK</div>
              {digest.top_categories.map((c) => (
                <div key={c.category} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14, padding: '4px 0' }}>
                  <span>{c.category}</span>
                  <span className="amount">₹{c.amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                </div>
              ))}
            </div>
          )}

          {digest.bills_due_soon.length > 0 && (
            <div>
              <div style={{ fontSize: 14, color: 'var(--ink-faint)', marginBottom: 6 }}>OVERDUE AND UPCOMING BILLS</div>
              {digest.bills_due_soon.map((b) => (
                <div key={`${b.id}-${b.due_date}`} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14, padding: '4px 0' }}>
                  <span>{b.name} ? {b.due_date} ? {b.status}</span>
                  <span className="amount">₹{b.amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
