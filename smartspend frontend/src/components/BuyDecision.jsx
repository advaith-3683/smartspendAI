import React, { useState } from 'react'
import { api } from '../api.js'

export default function BuyDecision({ userId, categories }) {
  const [itemName, setItemName] = useState('')
  const [cost, setCost] = useState('')
  const [category, setCategory] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setResult(null)
    if (!cost || !category) {
      setError('Pick a category and enter a cost.')
      return
    }
    try {
      const res = await api.buyDecision({
        user_id: userId,
        category,
        item_name: itemName.trim() || 'this item',
        item_cost: parseFloat(cost),
      })
      setResult(res)
    } catch (err) {
      setError(err.message)
    }
  }

  const handleClear = () => {
    setItemName('')
    setCost('')
    setCategory('')
    setResult(null)
    setError('')
  }

  return (
    <div className="card inline-form">
      <form onSubmit={handleSubmit}>
        <div className="form-row">
          <div className="field">
            <label htmlFor="buy-item">Item</label>
            <input
              id="buy-item"
              type="text"
              placeholder="New shoes"
              value={itemName}
              onChange={(e) => setItemName(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="buy-category">Category</label>
            <select id="buy-category" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">Select...</option>
              {categories.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="buy-cost">Cost (₹)</label>
            <input
              id="buy-cost"
              type="number"
              placeholder="4000"
              value={cost}
              onChange={(e) => setCost(e.target.value)}
            />
          </div>
          <button className="btn" type="submit">Check impact</button>
          <button className="btn secondary" type="button" onClick={handleClear}>Clear</button>
        </div>
      </form>
      {error && <div className="error-text">{error}</div>}
      {result && (
        <div className={`buy-result ${result.would_exceed_budget ? 'warn' : 'ok'}`}>
          {result.message}
        </div>
      )}
    </div>
  )
}
