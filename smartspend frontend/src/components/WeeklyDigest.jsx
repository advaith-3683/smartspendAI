import React, { useState } from 'react'
import { api } from '../api.js'

export default function WeeklyDigest({ userId }) {
  const [digest, setDigest] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const generate = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await api.getWeeklyDigest(userId)
      setDigest(res)
    } catch (err) {
      setError(err.message || 'Could not generate the digest right now.')
    } finally {
      setLoading(false)
    }
  }

  const change = digest ? digest.total_this_week - digest.total_last_week : 0
  const changePct = digest && digest.total_last_week > 0
    ? (change / digest.total_last_week) * 100
    : 0

  return (
    <div>
      <button className="btn" type="button" onClick={generate} disabled={loading}>
        {loading ? 'Coco is reviewing your week...' : digest ? 'Refresh this week\'s check-in' : 'Generate weekly check-in'}
      </button>

      {error && <div className="error-text" style={{ marginTop: 12 }}>{error}</div>}

      {digest && (
        <div className="card" style={{ marginTop: 16 }}>
          <div style={{ fontSize: 11, letterSpacing: '0.06em', color: 'var(--ink-faint)', fontFamily: 'IBM Plex Mono, monospace', marginBottom: 8 }}>
            {digest.period_start} — {digest.period_end}
          </div>

          <div className="buy-result ok" style={{ marginBottom: 20 }}>
            {digest.digest_text}
          </div>

          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 16 }}>
            <div>
              <div style={{ fontSize: 11, color: 'var(--ink-faint)' }}>THIS WEEK</div>
              <div style={{ fontSize: 20, fontFamily: 'IBM Plex Mono, monospace' }}>₹{digest.total_this_week.toLocaleString('en-IN')}</div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: 'var(--ink-faint)' }}>LAST WEEK</div>
              <div style={{ fontSize: 20, fontFamily: 'IBM Plex Mono, monospace', color: 'var(--ink-soft)' }}>₹{digest.total_last_week.toLocaleString('en-IN')}</div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: 'var(--ink-faint)' }}>CHANGE</div>
              <div style={{ fontSize: 20, fontFamily: 'IBM Plex Mono, monospace', color: change > 0 ? 'var(--status-bad)' : 'var(--status-good)' }}>
                {changePct >= 0 ? '+' : ''}{changePct.toFixed(0)}%
              </div>
            </div>
          </div>

          {digest.top_categories.length > 0 && (
            <div style={{ marginBottom: digest.bills_due_soon.length > 0 ? 12 : 0 }}>
              <div style={{ fontSize: 11, color: 'var(--ink-faint)', marginBottom: 6 }}>TOP CATEGORIES THIS WEEK</div>
              {digest.top_categories.map((c) => (
                <div key={c.category} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, padding: '4px 0' }}>
                  <span>{c.category}</span>
                  <span className="amount">₹{c.amount.toLocaleString('en-IN')}</span>
                </div>
              ))}
            </div>
          )}

          {digest.bills_due_soon.length > 0 && (
            <div>
              <div style={{ fontSize: 11, color: 'var(--ink-faint)', marginBottom: 6 }}>BILLS DUE THIS WEEK</div>
              {digest.bills_due_soon.map((b) => (
                <div key={b.id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, padding: '4px 0' }}>
                  <span>{b.name}</span>
                  <span className="amount">₹{b.amount.toLocaleString('en-IN')}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
