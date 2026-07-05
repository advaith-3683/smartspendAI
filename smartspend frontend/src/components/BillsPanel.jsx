import React, { useState, useEffect, useCallback } from 'react'
import { api } from '../api.js'
import { STANDARD_CATEGORIES } from '../constants.js'

const STATUS_LABEL = {
  paid: 'Paid',
  due: 'Due',
  overdue: 'Overdue',
}

const STATUS_CLASS = {
  paid: 'on_track',
  due: 'at_risk',
  overdue: 'over_budget',
}

export default function BillsPanel({ userId, year, month, onChange }) {
  const [bills, setBills] = useState([])
  const [name, setName] = useState('')
  const [category, setCategory] = useState('')
  const [amount, setAmount] = useState('')
  const [dueDay, setDueDay] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(() => {
    api.listBills(userId, year, month).then(setBills).catch((err) => setError(err.message))
  }, [userId, year, month])

  useEffect(() => {
    refresh()
  }, [refresh])

  const handleAdd = async (e) => {
    e.preventDefault()
    setError('')
    if (!name.trim() || !category.trim() || !amount || !dueDay) {
      setError('Fill in all fields to add a bill.')
      return
    }
    const day = parseInt(dueDay, 10)
    if (day < 1 || day > 31) {
      setError('Due day must be between 1 and 31.')
      return
    }
    try {
      await api.createBill({
        user_id: userId,
        name: name.trim(),
        category: category.trim(),
        amount: parseFloat(amount),
        due_day: day,
        year,
        month,
      })
      setName('')
      setCategory('')
      setAmount('')
      setDueDay('')
      refresh()
      onChange()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleTogglePaid = async (bill) => {
    setLoading(true)
    setError('')
    try {
      if (bill.status === 'paid') {
        await api.unpayBill(bill.id, year, month)
      } else {
        await api.payBill(bill.id, year, month)
      }
      refresh()
      onChange()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (billId) => {
    setLoading(true)
    try {
      await api.deleteBill(billId)
      refresh()
      onChange()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <form className="card inline-form" onSubmit={handleAdd} style={{ marginBottom: 16 }}>
        <div className="form-row">
          <div className="field">
            <label htmlFor="bill-name">Bill name</label>
            <input
              id="bill-name"
              type="text"
              placeholder="Broadband"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="bill-category">Category</label>
            <input
              id="bill-category"
              type="text"
              list="bill-category-suggestions"
              placeholder="Bills"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            />
            <datalist id="bill-category-suggestions">
              {STANDARD_CATEGORIES.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
          </div>
          <div className="field">
            <label htmlFor="bill-amount">Amount (₹)</label>
            <input
              id="bill-amount"
              type="number"
              placeholder="1062.82"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="bill-due-day">Due day of month</label>
            <input
              id="bill-due-day"
              type="number"
              min="1"
              max="31"
              placeholder="5"
              value={dueDay}
              onChange={(e) => setDueDay(e.target.value)}
            />
          </div>
          <button className="btn" type="submit">Add bill</button>
        </div>
        {error && <div className="error-text">{error}</div>}
      </form>

      {bills.length === 0 ? (
        <div className="empty-note">No recurring bills added yet.</div>
      ) : (
        <div className="card" style={{ overflowX: 'auto' }}>
          <table className="txn-table">
            <thead>
              <tr>
                <th>Bill</th>
                <th>Category</th>
                <th>Due day</th>
                <th style={{ textAlign: 'right' }}>Amount</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {bills.map((b) => (
                <tr key={b.id}>
                  <td>{b.name}</td>
                  <td>{b.category}</td>
                  <td>Day {b.due_day}</td>
                  <td className="amount">₹{b.amount.toLocaleString('en-IN')}</td>
                  <td>
                    <span className={`status-pill ${STATUS_CLASS[b.status]}`}>
                      {STATUS_LABEL[b.status]}
                    </span>
                  </td>
                  <td style={{ display: 'flex', gap: 6 }}>
                    <button
                      type="button"
                      className="btn secondary"
                      style={{ padding: '4px 10px', fontSize: 11 }}
                      onClick={() => handleTogglePaid(b)}
                      disabled={loading}
                    >
                      {b.status === 'paid' ? 'Mark unpaid' : 'Mark paid'}
                    </button>
                    <button
                      type="button"
                      className="btn secondary"
                      style={{ padding: '4px 10px', fontSize: 11 }}
                      onClick={() => handleDelete(b.id)}
                      disabled={loading}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
