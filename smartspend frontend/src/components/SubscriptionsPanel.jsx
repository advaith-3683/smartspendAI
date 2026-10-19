import React, { useEffect, useState, useCallback } from 'react'
import { api } from '../api.js'

export default function SubscriptionsPanel({ userId, transactions }) {
  const [loading, setLoading] = useState(true)
  const [subscriptions, setSubscriptions] = useState([])
  const [error, setError] = useState('')

  const refresh = useCallback(() => {
    setLoading(true)
    setError('')
    api
      .getSubscriptions(userId)
      .then(setSubscriptions)
      .catch((err) => setError(err.message)).finally(() => setLoading(false))
  }, [userId, transactions])

  useEffect(() => {
    refresh()
  }, [refresh])

  if (loading) return <p role="status">Loading subscription patterns...</p>
  if (error) return <div role="alert" className="error-text">{error} <button className="btn secondary" onClick={refresh}>Retry</button></div>

  if (subscriptions.length === 0) {
    return <div className="empty-note">No recurring subscriptions detected yet. Coco needs at least two months of transactions from the same merchant to spot a pattern.</div>
  }

  const totalMonthly = subscriptions.reduce((sum, s) => sum + s.average_amount, 0)

  return (
    <div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 12 }}>
        {subscriptions.map((s, i) => (
          <div
            key={i}
            className="buy-result warn"
            style={{ display: 'flex', gap: 10, alignItems: 'flex-start', justifyContent: 'space-between' }}
          >
            <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
              <span style={{ fontFamily: 'var(--font-body)', fontSize: 14, letterSpacing: '0.06em', flexShrink: 0, marginTop: 2 }}>
                ⟳ SUBSCRIPTION
              </span>
              <span>{s.message}</span>
            </div>
            <span className="amount" style={{ flexShrink: 0 }}>
              ₹{s.average_amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/mo
            </span>
          </div>
        ))}
      </div>
      <div className="empty-note" style={{ marginTop: 0 }}>
        Estimated total recurring spend: ₹{totalMonthly.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} / month across {subscriptions.length} subscription{subscriptions.length === 1 ? '' : 's'}.
      </div>
    </div>
  )
}
