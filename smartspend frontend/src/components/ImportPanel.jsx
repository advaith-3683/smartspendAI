import React, { useState } from 'react'
import { api } from '../api.js'

const SAMPLE_SMS = `Rs.450.00 debited from A/c XX1234 on 02-07-26 to SWIGGY
INR 300.00 spent on card XX1234 at ZOMATO on 03-07-2026
Rs 1200 debited towards UBER on 01-07-2026`

export default function ImportPanel({ userId, onImported }) {
  const [mode, setMode] = useState('sms') // 'sms' | 'statement'
  const [smsText, setSmsText] = useState('')
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState([]) // each row: { included, amount, category, merchant, date, note, source }
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [importedCount, setImportedCount] = useState(null)

  const handleParse = async () => {
    setError('')
    setImportedCount(null)
    setPreview([])
    setLoading(true)
    try {
      let rows
      if (mode === 'sms') {
        if (!smsText.trim()) {
          setError('Paste at least one SMS line.')
          setLoading(false)
          return
        }
        rows = await api.ingestSms(userId, smsText)
      } else {
        if (!file) {
          setError('Choose a .csv or .pdf statement file.')
          setLoading(false)
          return
        }
        rows = await api.ingestStatement(file)
      }
      setPreview(rows.map((r) => ({ ...r, included: true })))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const updateRow = (index, field, value) => {
    setPreview((prev) => prev.map((r, i) => (i === index ? { ...r, [field]: value } : r)))
  }

  const handleCommit = async () => {
    const selected = preview.filter((r) => r.included)
    if (selected.length === 0) {
      setError('Select at least one transaction to import.')
      return
    }
    setError('')
    setLoading(true)
    try {
      const payload = selected.map(({ included, ...rest }) => rest)
      const res = await api.commitIngest(userId, payload)
      setImportedCount(res.inserted)
      setPreview([])
      setSmsText('')
      setFile(null)
      onImported()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card inline-form">
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <button
          type="button"
          className={`btn ${mode === 'sms' ? '' : 'secondary'}`}
          onClick={() => { setMode('sms'); setPreview([]); setError('') }}
        >
          Paste SMS
        </button>
        <button
          type="button"
          className={`btn ${mode === 'statement' ? '' : 'secondary'}`}
          onClick={() => { setMode('statement'); setPreview([]); setError('') }}
        >
          Upload statement
        </button>
      </div>

      {mode === 'sms' ? (
        <div className="field" style={{ marginBottom: 12 }}>
          <label htmlFor="sms-text">Bank SMS text (one message per line)</label>
          <textarea
            id="sms-text"
            rows={5}
            style={{
              fontFamily: 'IBM Plex Mono, monospace',
              fontSize: 13,
              padding: 10,
              border: '1px solid var(--rule)',
              borderRadius: 6,
              resize: 'vertical',
            }}
            placeholder={SAMPLE_SMS}
            value={smsText}
            onChange={(e) => setSmsText(e.target.value)}
          />
        </div>
      ) : (
        <div className="field" style={{ marginBottom: 12 }}>
          <label htmlFor="statement-file">Bank statement (.csv or .pdf)</label>
          <input
            id="statement-file"
            type="file"
            accept=".csv,.pdf"
            onChange={(e) => setFile(e.target.files[0] || null)}
          />
        </div>
      )}

      <button className="btn" type="button" onClick={handleParse} disabled={loading}>
        {loading ? 'Parsing...' : 'Parse'}
      </button>

      {error && <div className="error-text">{error}</div>}
      {importedCount !== null && (
        <div className="buy-result ok" style={{ marginTop: 16 }}>
          Imported {importedCount} transaction{importedCount === 1 ? '' : 's'}.
        </div>
      )}

      {preview.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <table className="txn-table">
            <thead>
              <tr>
                <th></th>
                <th>Date</th>
                <th>Merchant / Description</th>
                <th>Category</th>
                <th style={{ textAlign: 'right' }}>Amount</th>
              </tr>
            </thead>
            <tbody>
              {preview.map((row, i) => (
                <tr key={i}>
                  <td>
                    <input
                      type="checkbox"
                      checked={row.included}
                      onChange={(e) => updateRow(i, 'included', e.target.checked)}
                    />
                  </td>
                  <td>{row.date}</td>
                  <td>{row.merchant || '—'}</td>
                  <td>
                    <input
                      type="text"
                      value={row.category}
                      onChange={(e) => updateRow(i, 'category', e.target.value)}
                      style={{
                        fontFamily: 'IBM Plex Mono, monospace',
                        fontSize: 12,
                        padding: '4px 6px',
                        border: '1px solid var(--rule)',
                        borderRadius: 6,
                        width: 110,
                      }}
                    />
                  </td>
                  <td className="amount">
                    <input
                      type="number"
                      value={row.amount}
                      onChange={(e) => updateRow(i, 'amount', parseFloat(e.target.value) || 0)}
                      style={{
                        fontFamily: 'IBM Plex Mono, monospace',
                        fontSize: 12,
                        padding: '4px 6px',
                        border: '1px solid var(--rule)',
                        borderRadius: 6,
                        width: 90,
                        textAlign: 'right',
                      }}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <button className="btn" type="button" onClick={handleCommit} disabled={loading} style={{ marginTop: 16 }}>
            {loading ? 'Importing...' : `Import ${preview.filter((r) => r.included).length} selected`}
          </button>
        </div>
      )}
    </div>
  )
}
