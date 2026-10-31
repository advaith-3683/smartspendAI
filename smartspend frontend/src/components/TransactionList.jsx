import { useConfirm } from './ConfirmDialog.jsx'
import React, { useMemo, useState, useRef } from 'react'

function TransactionEditor({ transaction, onChange, onSubmit, onCancel, busy }) {
  return <form className="edit-transaction form-row" onSubmit={onSubmit}>
    <label>Amount<input autoFocus type="number" min="0.01" step="0.01" max="1000000000" required value={transaction.amount} onChange={e => onChange({ ...transaction, amount: e.target.value })} /></label>
    <label>Category<input maxLength={100} required value={transaction.category} onChange={e => onChange({ ...transaction, category: e.target.value })} /></label>
    <label>Date<input type="date" min="1900-01-01" max="2200-12-31" required value={transaction.date} onChange={e => onChange({ ...transaction, date: e.target.value })} /></label>
    <label>Merchant<input maxLength={100} value={transaction.merchant || ''} onChange={e => onChange({ ...transaction, merchant: e.target.value })} /></label>
    <label>Frequency<select value={transaction.frequency} onChange={e => onChange({ ...transaction, frequency: e.target.value })}><option value="daily">Daily</option><option value="monthly">Monthly</option><option value="one_time">One-time</option></select></label>
    <label>Note<input maxLength={1000} value={transaction.note || ''} onChange={e => onChange({ ...transaction, note: e.target.value })} /></label>
    <button className="btn" disabled={busy}>Save changes</button><button className="btn secondary" type="button" disabled={busy} onClick={onCancel}>Cancel</button>
  </form>
}

export default function TransactionList({ transactions, onDelete, onEdit }) {
  const confirm = useConfirm()
  const locked = useRef(false)
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('')
  const [frequency, setFrequency] = useState('')
  const [editing, setEditing] = useState(null)
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState('')
  const [error, setError] = useState('')
  const rows = useMemo(() => transactions.filter(t =>
    (!category || t.category === category) &&
    (!frequency || t.frequency === frequency) &&
    `${t.category} ${t.note || ''} ${t.merchant || ''} ${t.date}`.toLowerCase().includes(search.toLowerCase())
  ), [transactions, search, category, frequency])
  async function run(action, message) {
    if (locked.current) return
    locked.current = true
    setBusy(true); setError(''); setFeedback('')
    try { await action(); setFeedback(message); setEditing(null) } catch (err) { setError(err.message) } finally { locked.current = false; setBusy(false) }
  }
  return <div className="card ledger-card">
    <div className="ledger-filters">
      <label>Search transactions<input type="search" placeholder="Search merchant, category or note" value={search} onChange={e => setSearch(e.target.value)} /></label>
      <label>Category<select value={category} onChange={e => setCategory(e.target.value)}><option value="">All categories</option>{[...new Set(transactions.map(t => t.category))].map(c => <option key={c}>{c}</option>)}</select></label>
      <label>Frequency<select value={frequency} onChange={e => setFrequency(e.target.value)}><option value="">All expenses</option><option value="daily">Daily</option><option value="monthly">Monthly</option><option value="one_time">One-time</option></select></label>
    </div>
    {error && <p role="alert" className="error-text">{error}</p>}{feedback && <p role="status" className="success-text">{feedback}</p>}
    {editing && <TransactionEditor transaction={editing} onChange={setEditing} busy={busy}
      onSubmit={e => { e.preventDefault(); run(() => onEdit(editing.id, { ...editing, amount: Number(editing.amount) }), 'Transaction updated.') }}
      onCancel={() => setEditing(null)} />}
    {!rows.length ? <div className="empty-note">{transactions.length ? 'No transactions match these filters.' : 'Your ledger is ready. Add your first expense to get started.'}</div> : <div className="table-scroll" role="region" aria-label="Transactions" tabIndex={0}><table className="txn-table responsive-table"><thead><tr><th>Date</th><th>Category</th><th>Details</th><th>Frequency</th><th className="align-right">Amount</th><th>Actions</th></tr></thead><tbody>{rows.map(t => <tr key={t.id}>
      <td data-label="Date">{t.date}</td><td data-label="Category">{t.category}</td><td data-label="Details">{t.note || t.merchant || '-'}<small className="transaction-source">{t.source}</small></td><td data-label="Frequency">{t.frequency.replace('_', '-')}</td><td data-label="Amount" className="amount">INR {Number(t.amount).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td><td data-label="Actions" className="row-actions">
      {onEdit && <button className="btn secondary" disabled={busy || t.source === 'bill'} title={t.source === 'bill' ? 'Manage linked payments in Budgets & Bills' : 'Edit transaction'} onClick={() => setEditing({ ...t })}>Edit</button>}
      <button className="btn secondary" disabled={busy} aria-label={`Delete ${t.category} expense dated ${t.date}`} onClick={async () => { if (await confirm('Delete this expense? This cannot be undone.')) run(() => onDelete(t.id), 'Transaction deleted.') }}>Delete</button>
    </td></tr>)}</tbody></table></div>}
    <p className="period-note">{rows.length} of {transactions.length} transactions in the selected month</p>
  </div>
}
