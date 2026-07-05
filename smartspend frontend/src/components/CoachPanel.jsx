import React, { useState } from 'react'
import { api } from '../api.js'

export default function CoachPanel({ userId, year, month }) {
  const [advice, setAdvice] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleAsk = async () => {
    setLoading(true)
    setError('')
    setAdvice('')
    try {
      const res = await api.getCoachAdvice(userId, year, month)
      setAdvice(res.advice)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card inline-form">
      <button className="btn" type="button" onClick={handleAsk} disabled={loading}>
        {loading ? 'Thinking...' : 'How can I save more money?'}
      </button>
      {error && <div className="error-text">{error}</div>}
      {advice && (
        <div className="buy-result ok" style={{ marginTop: 16, whiteSpace: 'pre-wrap' }}>
          {advice}
        </div>
      )}
    </div>
  )
}
