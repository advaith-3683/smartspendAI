import React from 'react'

export default function TransactionList({ transactions, onDelete }) {
  if (transactions.length === 0) {
    return <div className="empty-note">No expenses logged yet. Add one above to get started.</div>
  }

  return (
    <div className="card" style={{ overflowX: 'auto' }}>
      <table className="txn-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Category</th>
            <th>Note</th>
            <th>Source</th>
            <th>Frequency</th>
            <th style={{ textAlign: 'right' }}>Amount</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {transactions.map((t) => (
            <tr key={t.id}>
              <td>{t.date}</td>
              <td>{t.category}</td>
              <td>{t.note || t.merchant || '—'}</td>
              <td>{t.source}</td>
              <td>
                {t.frequency === 'monthly' ? (
                  <span className="status-pill at_risk">MONTHLY</span>
                ) : (
                  '—'
                )}
              </td>
              <td className="amount">₹{t.amount.toLocaleString('en-IN')}</td>
              <td>
                <button
                  type="button"
                  className="btn secondary"
                  style={{ padding: '4px 10px', fontSize: 11 }}
                  onClick={() => onDelete(t.id)}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
