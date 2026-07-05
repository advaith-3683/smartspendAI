import React, { useState } from 'react'
import { STANDARD_CATEGORIES } from '../constants.js'

const todayIso = () => new Date().toISOString().slice(0, 10)

export default function TransactionForm({ categories, onSubmit }) {
  const [amount, setAmount] = useState('')
  const [category, setCategory] = useState('')
  const [date, setDate] = useState(todayIso())
  const [note, setNote] = useState('')
  const [frequency, setFrequency] = useState('daily')
  const [error, setError] = useState('')

  const suggestions = Array.from(new Set([...categories, ...STANDARD_CATEGORIES]))

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
    setDate(todayIso())
    setNote('')
    setFrequency('daily')
    setError('')
  }

  return (
    <form className="card inline-form" onSubmit={handleSubmit}>
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
      {error && <div className="error-text">{error}</div>}
      <div style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: 11, color: 'var(--ink-faint)', marginTop: 10 }}>
        Typed a category with no budget set? It'll show up under "Miscellaneous" on the dashboard.
      </div>
    </form>
  )
}
