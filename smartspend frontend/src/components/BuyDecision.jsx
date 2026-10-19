import React, { useEffect, useState, useRef } from 'react'
import { api } from '../api.js'

export default function BuyDecision({ userId, categories, year, month }) {
  const revision = useRef(0)
  const busy = useRef(false)
  const [pending, setPending] = useState(false)
  const [itemName, setItemName] = useState('')
  const [cost, setCost] = useState('')
  const [category, setCategory] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { revision.current += 1; setResult(null); setError('') }, [year, month])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (busy.current) return
    setError('')
    setResult(null)
    if (!cost || !category) {
      setError('Pick a category and enter a cost.')
      return
    }
    const version = revision.current
    busy.current = true; setPending(true)
    try {
      const res = await api.buyDecision({
        user_id: userId, year, month,
        category,
        item_name: itemName.trim() || 'this item',
        item_cost: parseFloat(cost),
      })
      if (version === revision.current) setResult(res)
    } catch (err) {
      if (version === revision.current) setError(err.message)
    } finally { busy.current = false; setPending(false) }
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
              id="buy-item" maxLength={100}
              type="text"
              placeholder="New shoes"
              value={itemName}
              onChange={(e) => setItemName(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="buy-category">Category</label>
            <input id="buy-category" list="buy-categories" required maxLength={100} value={category} onChange={e => setCategory(e.target.value)} />
            <datalist id="buy-categories">{categories.map(c => <option key={c} value={c} />)}</datalist>
          </div>
          <div className="field">
            <label htmlFor="buy-cost">Cost (₹)</label>
            <input
              id="buy-cost"
              min="0.01" step="0.01" max="1000000000"
              type="number" required
              placeholder="4000"
              value={cost}
              onChange={(e) => setCost(e.target.value)}
            />
          </div>
          <button className="btn" type="submit" disabled={pending}>Check impact</button>
          <button className="btn secondary" type="button" onClick={handleClear}>Clear</button>
        </div>
      </form>
      {error && <div role="alert" className="error-text">{error}</div>}
      {result && (
        <div className={`buy-result ${result.would_exceed_budget ? 'warn' : 'ok'}`}>
          {result.message}
        </div>
      )}
    </div>
  )
}
