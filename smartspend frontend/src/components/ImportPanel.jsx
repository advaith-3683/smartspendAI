import { useConfirm } from './ConfirmDialog.jsx'
import React, { useState, useRef } from 'react'
import { api } from '../api.js'

const SAMPLE_SMS = `Rs.450.00 debited from A/c XX1234 on 02-07-26 to SWIGGY
INR 300.00 spent on card XX1234 at ZOMATO on 03-07-2026
Rs 1200 debited towards UBER on 01-07-2026`

export default function ImportPanel({ userId, onImported }) {
  const confirm = useConfirm()
  const busy = useRef(false)
  const batchKey = useRef(null)
  const [mode, setMode] = useState('sms') // 'sms' | 'statement'
  const [smsText, setSmsText] = useState('')
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState([]) // each row: { included, amount, category, merchant, date, note, source }
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [parsed, setParsed] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const [importedCount, setImportedCount] = useState(null)

  const handleParse = async () => {
    if (busy.current) return
    busy.current = true
    setError('')
    setImportedCount(null)
    setPreview([])
    setParsed(false)
    setUncertain(false)
    setLoading(true)
    try {
      let rows
      if (mode === 'sms') {
        if (!smsText.trim()) {
          setError('Paste at least one SMS line.')
          setLoading(false)
          busy.current = false
          return
        }
        rows = await api.ingestSms(userId, smsText)
      } else {
        if (!file) {
          setError('Choose a .csv or .pdf statement file.')
          setLoading(false)
          busy.current = false
          return
        }
        if (file.size > 5 * 1024 * 1024 || !/\.(csv|pdf)$/i.test(file.name)) throw new Error('Choose a CSV or PDF no larger than 5 MiB.')
        rows = await api.ingestStatement(file)
      }
      setParsed(true)
      batchKey.current = crypto.randomUUID()
      setPreview(rows.map((r) => ({ ...r, included: true })))
    } catch (err) {
      setError(err.message)
    } finally {
      busy.current = false
      setLoading(false)
    }
  }

  const updateRow = (index, field, value) => {
    setPreview((prev) => prev.map((r, i) => (i === index ? { ...r, [field]: value } : r)))
  }

  const handleCommit = async () => {
    if (busy.current) return
    const selected = preview.filter((r) => r.included)
    if (selected.length === 0) {
      setError('Select at least one transaction to import.')
      return
    }
    if (selected.some(row => !row.category?.trim() || !/^\d{4}-\d{2}-\d{2}$/.test(row.date) || !Number.isFinite(Number(row.amount)) || Number(row.amount) <= 0 || Number(row.amount) > 1000000000 || !/^\d+(\.\d{1,2})?$/.test(String(row.amount)))) {
      setError('Each selected row needs a date, category and positive amount with at most two decimals.'); return
    }
    busy.current = true
    setError('')
    setLoading(true)
    setUncertain(true)
    try {
      const payload = selected.map(({ included, ...rest }) => rest)
      const res = await api.commitIngest(userId, payload, batchKey.current)
      setUncertain(false)
      setParsed(false)
      setImportedCount(res.inserted)
      setPreview([])
      setSmsText('')
      setFile(null)
      onImported()
    } catch (err) {
      if ([400, 422].includes(err.status)) setUncertain(false)
      setError(err.message)
    } finally {
      busy.current = false
      setLoading(false)
    }
  }

  return (
    <div className="card inline-form">
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <button
          type="button"
          className={`btn ${mode === 'sms' ? '' : 'secondary'}`}
          disabled={loading || uncertain}
          onClick={() => { setParsed(false); setImportedCount(null); setMode('sms'); setPreview([]); setError('') }}
        >
          Paste SMS
        </button>
        <button
          type="button"
          className={`btn ${mode === 'statement' ? '' : 'secondary'}`}
          disabled={loading || uncertain}
          onClick={() => { setParsed(false); setImportedCount(null); setMode('statement'); setPreview([]); setError('') }}
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
            maxLength={100000}
            disabled={loading || uncertain}
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: 16,
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
            disabled={loading || uncertain}
            onChange={(e) => setFile(e.target.files[0] || null)}
          />
        </div>
      )}

      <button className="btn" type="button" onClick={handleParse} disabled={loading || uncertain}>
        {loading ? 'Parsing...' : 'Parse'}
      </button>

      {parsed && !preview.length && <p role="status">No clear debit transactions found. Check the source format. Credits and ambiguous rows are excluded.</p>}
      {uncertain && <p role="status">This batch is locked after a save attempt. Retry the same batch to safely confirm its result.</p>}
      {error && <div role="alert" className="error-text">{error}</div>}
      {importedCount !== null && (
        <div role="status" className="buy-result ok" style={{ marginTop: 16 }}>
          Imported {importedCount} transaction{importedCount === 1 ? '' : 's'}.
        </div>
      )}

      {preview.length > 0 && (
        <div role="region" aria-label="Editable import preview" tabIndex={0} style={{ marginTop: 20, overflowX: 'auto' }}>
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
                      disabled={loading || uncertain}
                      aria-label={`Include import row ${i + 1}`}
                      checked={row.included}
                      onChange={(e) => updateRow(i, 'included', e.target.checked)}
                    />
                  </td>
                  <td><input aria-label={`Date for row ${i + 1}`} type="date" value={row.date} disabled={loading || uncertain} onChange={e => updateRow(i, 'date', e.target.value)} /></td>
                  <td><input aria-label={`Merchant for row ${i + 1}`} maxLength={100} value={row.merchant || ''} disabled={loading || uncertain} onChange={e => updateRow(i, 'merchant', e.target.value)} /></td>
                  <td>
                    <input
                      type="text"
                      aria-label={`Category for row ${i + 1}`}
                      maxLength={100} disabled={loading || uncertain}
                      value={row.category}
                      onChange={(e) => updateRow(i, 'category', e.target.value)}
                      style={{
                        fontFamily: 'var(--font-body)',
                        fontSize: 16,
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
                      min="0.01" step="0.01" max="1000000000" disabled={loading || uncertain}
                      aria-label={`Amount for row ${i + 1}`}
                      value={row.amount}
                      onChange={(e) => updateRow(i, 'amount', parseFloat(e.target.value) || 0)}
                      style={{
                        fontFamily: 'var(--font-body)',
                        fontSize: 16,
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
          <button className="btn secondary" type="button" disabled={loading} onClick={async () => {
            if (uncertain && !await confirm('The save may already have succeeded. Check your ledger before importing again. Discard this preview?')) return
            setPreview([]); setUncertain(false); setParsed(false); setError(''); batchKey.current = null
          }}>Discard preview</button>
        </div>
      )}
    </div>
  )
}
