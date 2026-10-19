import { useConfirm } from './ConfirmDialog.jsx'
import React, { useState, useEffect, useCallback, useRef } from 'react'
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
  const confirm = useConfirm()
  const revision = useRef(0)
  const mutation = useRef(false)
  const [notice, setNotice] = useState('')
  const [reading, setReading] = useState(true)
  const [bills, setBills] = useState([])
  const [name, setName] = useState('')
  const [category, setCategory] = useState('')
  const [amount, setAmount] = useState('')
  const [dueDay, setDueDay] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(() => {
    setError('')
    const version = ++revision.current
    setReading(true)
    return api.listBills(userId, year, month).then(rows => { if (version === revision.current) setBills(rows) }).catch(err => { if (version === revision.current) setError(err.message) }).finally(() => { if (version === revision.current) setReading(false) })
  }, [userId, year, month])

  useEffect(() => {
    refresh()
    return () => { revision.current += 1 }
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
    if (mutation.current) return
    mutation.current = true; setLoading(true); setNotice('')
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
      setNotice('Recurring bill saved.')
      setName('')
      setCategory('')
      setAmount('')
      setDueDay('')
      refresh()
      onChange()
    } catch (err) {
      setError(err.message)
    } finally { mutation.current = false; setLoading(false) }
  }

  const handleTogglePaid = async (bill) => {
    if (bill.status === 'paid' && !await confirm('Mark this bill unpaid and remove its linked expense?')) return
    if (mutation.current) return
    mutation.current = true
    setLoading(true)
    setError('')
    try {
      if (bill.status === 'paid') {
        await api.unpayBill(bill.id, year, month)
        setNotice('Bill marked unpaid. Its linked payment expense was removed.')
      } else {
        await api.payBill(bill.id, year, month)
        setNotice('Bill paid. Its expense is saved.')
      }
      refresh()
      onChange()
    } catch (err) {
      setError(err.message)
    } finally {
      mutation.current = false
      setLoading(false)
    }
  }

  const handleDelete = async (billId) => {
    if (!await confirm('Delete this recurring bill? Historical expenses will remain.')) return
    if (mutation.current) return
    mutation.current = true
    setLoading(true)
    try {
      await api.deleteBill(billId)
      setNotice('Recurring bill deleted. Historical spending was retained.')
      refresh()
      onChange()
    } catch (err) {
      setError(err.message)
    } finally {
      mutation.current = false
      setLoading(false)
    }
  }

  return (
    <div>
      {notice && <p role="status" className="success-text">{notice}</p>}
      <form className="card inline-form" onSubmit={handleAdd} style={{ marginBottom: 16 }}>
        <div className="form-row">
          <div className="field">
            <label htmlFor="bill-name">Bill name</label>
            <input
              id="bill-name" maxLength={100} required
              type="text"
              placeholder="Broadband"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="bill-category">Category</label>
            <input
              id="bill-category" maxLength={100} required
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
              min="0.01" step="0.01" max="1000000000"
              type="number" required
              placeholder="1062.82"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="bill-due-day">Due day of month</label>
            <input
              id="bill-due-day"
              type="number" required
              min="1"
              max="31"
              placeholder="5"
              value={dueDay}
              onChange={(e) => setDueDay(e.target.value)}
            />
          </div>
          <button className="btn" type="submit" disabled={loading}>Add bill</button>
        </div>
        {error && <div role="alert" className="error-text">{error} <button type="button" className="btn secondary" onClick={refresh}>Retry</button></div>}
      </form>

      <p>Deleting a recurring bill keeps its historical expense transactions. Marking a bill unpaid removes its linked payment expense.</p>
      {reading ? <p role="status">Loading saved bills...</p> : bills.length === 0 ? (
        <div className="empty-note">No recurring bills added yet.</div>
      ) : (
        <div className="card" role="region" aria-label="Recurring bills" tabIndex={0} style={{ overflowX: 'auto' }}>
          <table className="txn-table responsive-table">
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
                  <td data-label="Bill">{b.name}</td>
                  <td data-label="Category">{b.category}</td>
                  <td data-label="Due day">Day {b.due_day}</td>
                  <td data-label="Amount" className="amount">₹{b.amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                  <td data-label="Status">
                    <span className={`status-pill ${STATUS_CLASS[b.status]}`}>
                      {STATUS_LABEL[b.status]}
                    </span>
                  </td>
                  <td data-label="Actions" style={{ display: 'flex', gap: 6 }}>
                    <button
                      type="button"
                      className="btn secondary"
                      style={{ padding: '4px 10px', fontSize: 16 }}
                      onClick={() => handleTogglePaid(b)}
                      disabled={loading}
                    >
                      {b.status === 'paid' ? 'Mark unpaid' : 'Mark paid'}
                    </button>
                    <button
                      type="button"
                      className="btn secondary"
                      style={{ padding: '4px 10px', fontSize: 16 }}
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
