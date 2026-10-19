import React, { useState, useEffect, useRef } from 'react'
import { STANDARD_CATEGORIES } from '../constants.js'

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

// Local date formatting (not toISOString, which converts to UTC and can
// roll the date back a day depending on the user's timezone).
const toLocalIso = (d) => {
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const todayIso = () => toLocalIso(new Date())

// Default the date field to match whichever month/year the dashboard is
// currently viewing — today's date if that's the current real month,
// otherwise the 1st of the viewed month. Without this, adding a transaction
// while looking at June silently used today's real-world date (July).
const defaultDateFor = (year, month) => {
  const now = new Date()
  if (year === now.getFullYear() && month === now.getMonth() + 1) {
    return todayIso()
  }
  return toLocalIso(new Date(year, month - 1, 1))
}

export default function TransactionForm({ categories, year, month, onSubmit }) {
  const [amount, setAmount] = useState('')
  const [category, setCategory] = useState('')
  const [date, setDate] = useState(defaultDateFor(year, month))
  const [note, setNote] = useState('')
  const [frequency, setFrequency] = useState('daily')
  const busy = useRef(false)
  const [saving, setSaving] = useState(false)
  const [success, setSuccess] = useState('')
  const [error, setError] = useState('')

  // Keep the date field aligned with the month being viewed on the dashboard.
  useEffect(() => {
    setDate(defaultDateFor(year, month))
  }, [year, month])

  const suggestions = Array.from(new Set([...categories, ...STANDARD_CATEGORIES]))

  const dateOutsideViewedMonth = (() => {
    if (!date) return false
    const [y, m] = date.split('-').map(Number)
    return y !== year || m !== month
  })()

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (busy.current) return
    setError('')
    if (!amount || !category.trim()) {
      setError('Amount and category are required.')
      return
    }
    busy.current = true; setSaving(true); setSuccess('')
    try {
      await onSubmit({
        amount: parseFloat(amount),
        category: category.trim(),
        date,
        note: note.trim() || null,
        source: 'manual',
        frequency,
      })
      setSuccess('Expense saved to your account.')
      setAmount('')
      setNote('')
    } catch (err) {
      setError(err.message)
    } finally { busy.current = false; setSaving(false) }
  }

  const handleClear = () => {
    setAmount('')
    setCategory('')
    setDate(defaultDateFor(year, month))
    setNote('')
    setFrequency('daily')
    setError('')
  }

  return (
    <form className="card inline-form" onSubmit={handleSubmit}>
      <div style={{ fontSize: 14, letterSpacing: '0.06em', color: 'var(--ink-faint)', fontFamily: 'var(--font-body)', marginBottom: 10 }}>
        ADDING TO: {MONTH_NAMES[month - 1]} {year}
      </div>
      <div className="form-row">
        <div className="field">
          <label htmlFor="txn-amount">Amount (₹)</label>
          <input
            id="txn-amount"
              min="0.01" step="0.01" max="1000000000"
            type="number" required
            placeholder="450"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="txn-category">Category</label>
          <input
            id="txn-category" maxLength={100} required
            type="text"
            list="txn-category-suggestions"
            placeholder="Food"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          />
          <datalist id="txn-category-suggestions">
            {suggestions.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </div>
        <div className="field">
          <label htmlFor="txn-date">Date</label>
          <input
            id="txn-date" required min="1900-01-01" max="2200-12-31"
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="txn-frequency">Frequency</label>
          <select id="txn-frequency" value={frequency} onChange={(e) => setFrequency(e.target.value)}>
            <option value="daily">Daily spending (project this pace)</option>
            <option value="one_time">One-time expense (count once)</option>
            <option value="monthly">Monthly (recurring, e.g. subscription)</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="txn-note">Note (optional)</label>
          <input
            id="txn-note" maxLength={1000}
            type="text"
            placeholder="Swiggy dinner"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </div>
        <button className="btn" type="submit" disabled={saving}>Log expense</button>
        <button className="btn secondary" type="button" onClick={handleClear}>Clear</button>
      </div>
      {dateOutsideViewedMonth && (
        <div className="buy-result warn" style={{ marginTop: 10, padding: '8px 12px', fontSize: 14 }}>
          This date is in {(() => { const [y, m] = date.split('-').map(Number); return `${MONTH_NAMES[m - 1]} ${y}` })()}, not the month you're viewing ({MONTH_NAMES[month - 1]} {year}). It'll show up there instead.
        </div>
      )}
      {success && <p role="status" className="success-text">{success}</p>}
      {error && <div role="alert" className="error-text">{error}</div>}
      <div style={{ fontFamily: 'var(--font-body)', fontSize: 14, color: 'var(--ink-faint)', marginTop: 10 }}>
        Typed a category with no budget set? It stays in that category and is included in total spending.
      </div>
    </form>
  )
}
