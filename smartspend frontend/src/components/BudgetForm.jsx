import React, { useState } from 'react'
import { STANDARD_CATEGORIES } from '../constants.js'

export default function BudgetForm({ onSubmit }) {
  const [category, setCategory] = useState('')
  const [limit, setLimit] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (!category.trim() || !limit) {
      setError('Enter a category and a limit.')
      return
    }
    try {
      await onSubmit({ category: category.trim(), monthly_limit: parseFloat(limit) })
      setCategory('')
      setLimit('')
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <form className="card inline-form" onSubmit={handleSubmit}>
      <div className="form-row">
        <div className="field">
          <label htmlFor="budget-category">Category</label>
          <input
            id="budget-category"
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
            type="number"
            placeholder="8000"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
          />
        </div>
        <button className="btn" type="submit">Set budget</button>
      </div>
      {error && <div className="error-text">{error}</div>}
    </form>
  )
}
