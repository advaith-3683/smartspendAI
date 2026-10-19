import React, { useState, useRef } from 'react'
import { STANDARD_CATEGORIES } from '../constants.js'

export default function BudgetForm({ onSubmit }) {
  const [category, setCategory] = useState('')
  const [limit, setLimit] = useState('')
  const busy = useRef(false)
  const [saving, setSaving] = useState(false)
  const [success, setSuccess] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (busy.current) return
    setError('')
    if (!category.trim() || !limit) {
      setError('Enter a category and a limit.')
      return
    }
    busy.current = true; setSaving(true); setSuccess('')
    try {
      await onSubmit({ category: category.trim(), monthly_limit: parseFloat(limit) })
      setSuccess('Budget saved to your account.')
      setCategory('')
      setLimit('')
    } catch (err) {
      setError(err.message)
    } finally { busy.current = false; setSaving(false) }
  }

  return (
    <form className="card inline-form" onSubmit={handleSubmit}>
      <div className="form-row">
        <div className="field">
          <label htmlFor="budget-category">Category</label>
          <input
            id="budget-category" maxLength={100} required
            type="text"
            list="budget-category-suggestions"
            placeholder="Food"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          />
          <datalist id="budget-category-suggestions">
            {STANDARD_CATEGORIES.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </div>
        <div className="field">
          <label htmlFor="budget-limit">Monthly limit (₹)</label>
          <input
            id="budget-limit"
              min="0.01" step="0.01" max="1000000000"
            type="number" required
            placeholder="8000"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
          />
        </div>
        <button className="btn" type="submit" disabled={saving}>Set budget</button>
      </div>
      {success && <p role="status" className="success-text">{success}</p>}
      {error && <div role="alert" className="error-text">{error}</div>}
    </form>
  )
}
