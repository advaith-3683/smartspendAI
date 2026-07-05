import React from 'react'

export default function AnomalyBanner({ anomalies }) {
  if (!anomalies || anomalies.length === 0) return null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 32 }}>
      {anomalies.map((a, i) => (
        <div
          key={i}
          className="buy-result warn"
          style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}
        >
          <span style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: 11, letterSpacing: '0.06em', flexShrink: 0, marginTop: 2 }}>
            ⚠ {a.type === 'spike' ? 'SPIKE' : 'PATTERN'}
          </span>
          <span>{a.message}</span>
        </div>
      ))}
    </div>
  )
}
