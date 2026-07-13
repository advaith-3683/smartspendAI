import React, { useState, useEffect } from 'react'
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
    setError('')
    if (!amount || !category.trim()) {
      setError('Amount and category are required.')
      return
    }
    try {
      await onSubmit({
        amount: parseFloat(amount),
        category: category.trim(),
        date,
        note: note.trim() || null,
        source: 'manual',
        frequency,
      })
      setAmount('')
      setNote('')
    } catch (err) {
      setError(err.message)
    }
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
      <div style={{ fontSize: 11, letterSpacing: '0.06em', color: 'var(--ink-faint)', fontFamily: 'IBM Plex Mono, monospace', marginBottom: 10 }}>
        ADDING TO: {MONTH_NAMES[month - 1]} {year}
      </div>
      <div className="form-row">
        <div className="field">
          <label htmlFor="txn-amount">Amount (₹)</label>
          <input
            id="txn-amount"
            type="number"
            placeholder="450"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="txn-category">Category</label>
          <input
            id="txn-category"
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
            id="txn-date"
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="txn-frequency">Frequency</label>
          <select id="txn-frequency" value={frequency} onChange={(e) => setFrequency(e.target.value)}>
            <option value="daily">One-time / daily</option>
            <option value="monthly">Monthly (recurring, e.g. subscription)</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="txn-note">Note (optional)</label>
          <input
            id="txn-note"
            type="text"
            placeholder="Swiggy dinner"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </div>
        <button className="btn" type="submit">Log expense</button>
        <button className="btn secondary" type="button" onClick={handleClear}>Clear</button>
      </div>
      {dateOutsideViewedMonth && (
        <div className="buy-result warn" style={{ marginTop: 10, padding: '8px 12px', fontSize: 12 }}>
          This date is in {(() => { const [y, m] = date.split('-').map(Number); return `${MONTH_NAMES[m - 1]} ${y}` })()}, not the month you're viewing ({MONTH_NAMES[month - 1]} {year}). It'll show up there instead.
        </div>
      )}
      {error && <div className="error-text">{error}</div>}
      <div style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: 11, color: 'var(--ink-faint)', marginTop: 10 }}>
        Typed a category with no budget set? It'll show up under "Miscellaneous" on the dashboard.
      </div>
    </form>
  )
}
