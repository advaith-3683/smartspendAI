import React from 'react'

function buildAlert(p) {
  const { category, status, monthly_limit, spent_so_far, days_elapsed, days_in_month } = p

  if (status !== 'over_budget' && status !== 'at_risk') return null

  // Already actually overspent (not just projected)
  if (spent_so_far > monthly_limit) {
    const overBy = spent_so_far - monthly_limit
    return {
      category,
      severity: 'bad',
      message: `You've already gone ₹${overBy.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} over your ${category} budget with ${days_in_month - days_elapsed} days still left this month.`,
    }
  }

  return {
    category,
    severity: 'warn',
    message: `Your ${category} spending is projected at INR ${p.projected_spend.toLocaleString('en-IN', { maximumFractionDigits: 2 })} against a budget of INR ${monthly_limit.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}. Monthly and one-time payments are counted once.`,
  }
}

export default function BurnAlertBanner({ pace }) {
  const alerts = pace.map(buildAlert).filter(Boolean)
  if (alerts.length === 0) return null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 20 }}>
      {alerts.map((a, i) => (
        <div
          key={i}
          className={`buy-result ${a.severity === 'bad' ? 'warn' : 'ok'}`}
          style={{
            display: 'flex',
            gap: 10,
            alignItems: 'flex-start',
            background: a.severity === 'bad' ? 'var(--status-bad-bg)' : 'var(--status-warn-bg)',
            color: a.severity === 'bad' ? 'var(--status-bad)' : 'var(--status-warn)',
          }}
        >
          <span style={{ fontFamily: 'var(--font-body)', fontSize: 14, letterSpacing: '0.06em', flexShrink: 0, marginTop: 2 }}>
            ⏱ PACE
          </span>
          <span>{a.message}</span>
        </div>
      ))}
    </div>
  )
}
