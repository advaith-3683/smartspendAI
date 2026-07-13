import React, { useState } from 'react'
import { api } from '../api.js'

function CategoryBar({ cat, maxValue }) {
  const currentPct = maxValue > 0 ? (cat.current_monthly_avg / maxValue) * 100 : 0
  const targetPct = maxValue > 0 ? (cat.target_monthly / maxValue) * 100 : 0
  const hasCut = cat.cut_amount > 0

  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
        <span style={{ color: 'var(--ink)' }}>{cat.category}</span>
        <span style={{ fontFamily: 'IBM Plex Mono, monospace', color: 'var(--ink-soft)' }}>
          ₹{cat.current_monthly_avg.toLocaleString('en-IN')}
          {hasCut && (
            <>
              {' → '}
              <span style={{ color: 'var(--gold)' }}>₹{cat.target_monthly.toLocaleString('en-IN')}</span>
            </>
          )}
        </span>
      </div>
      <div style={{ position: 'relative', height: 14, background: 'var(--bg-elevated-2)', borderRadius: 4, overflow: 'hidden' }}>
        <div
          style={{
            position: 'absolute',
            top: 0, left: 0, bottom: 0,
            width: `${currentPct}%`,
            background: 'var(--border-strong)',
          }}
        />
        <div
          style={{
            position: 'absolute',
            top: 0, left: 0, bottom: 0,
            width: `${targetPct}%`,
            background: hasCut ? 'var(--gold)' : 'var(--status-good)',
            transition: 'width 0.4s ease',
          }}
        />
      </div>
      {hasCut && (
        <div style={{ fontSize: 11, color: 'var(--gold)', marginTop: 2 }}>
          Cut ₹{cat.cut_amount.toLocaleString('en-IN')} ({cat.cut_percent}%)
        </div>
      )}
    </div>
  )
}

export default function SavingsGoalPlanner({ userId }) {
  const [amount, setAmount] = useState('')
  const [months, setMonths] = useState('')
  const [plan, setPlan] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    const amt = parseFloat(amount)
    const mo = parseInt(months, 10)
    if (!amt || amt <= 0 || !mo || mo <= 0) {
      setError('Enter a valid savings amount and number of months.')
      return
    }
    setLoading(true)
    setPlan(null)
    try {
      const res = await api.getSavingsGoalPlan(userId, amt, mo)
      setPlan(res)
    } catch (err) {
      setError(err.message || 'Could not calculate a plan right now.')
    } finally {
      setLoading(false)
    }
  }

  const maxValue = plan ? Math.max(...plan.categories.map((c) => c.current_monthly_avg), 1) : 1

  return (
    <div>
      <form className="card inline-form" onSubmit={handleSubmit} style={{ marginBottom: 16 }}>
        <div className="form-row">
          <div className="field">
            <label htmlFor="goal-amount">Savings goal (₹)</label>
            <input
              id="goal-amount"
              type="number"
              placeholder="50000"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="goal-months">In how many months</label>
            <input
              id="goal-months"
              type="number"
              min="1"
              placeholder="6"
              value={months}
              onChange={(e) => setMonths(e.target.value)}
            />
          </div>
          <button className="btn" type="submit" disabled={loading}>
            {loading ? 'Calculating...' : 'Build my plan'}
          </button>
        </div>
        {error && <div className="error-text">{error}</div>}
      </form>

      {plan && (
        <div className="card">
          <div
            className={`buy-result ${plan.achievable ? 'ok' : 'warn'}`}
            style={{ marginBottom: 20 }}
          >
            {plan.advice}
          </div>

          <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', marginBottom: 20, fontSize: 12, color: 'var(--ink-soft)' }}>
            <div>Need to save <strong style={{ color: 'var(--ink)' }}>₹{plan.monthly_savings_needed.toLocaleString('en-IN')}</strong>/mo</div>
            <div>Currently saving <strong style={{ color: 'var(--ink)' }}>₹{plan.current_monthly_savings.toLocaleString('en-IN')}</strong>/mo</div>
            {plan.additional_cut_needed > 0 && (
              <div>Extra cut needed <strong style={{ color: 'var(--gold)' }}>₹{plan.additional_cut_needed.toLocaleString('en-IN')}</strong>/mo</div>
            )}
          </div>

          {plan.categories.length === 0 ? (
            <div className="empty-note">No spending history yet to base a plan on — log a few transactions first.</div>
          ) : (
            plan.categories.map((c) => <CategoryBar key={c.category} cat={c} maxValue={maxValue} />)
          )}
        </div>
      )}
    </div>
  )
}
