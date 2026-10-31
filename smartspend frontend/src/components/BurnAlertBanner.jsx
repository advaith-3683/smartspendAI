import React from 'react'
import Icon from './Icon.jsx'
import { formatMoney } from '../money.js'

export default function BurnAlertBanner({ pace }) {
  const alerts = pace.filter(row => row.status === 'over_budget' || row.status === 'at_risk')
    .sort((a, b) => Number(b.status === 'over_budget') - Number(a.status === 'over_budget'))
  if (!alerts.length) return null
  return <section className="home-alerts" aria-label="Budget alerts" aria-live="polite">
    <div className="panel-heading"><div><h2>Keep an eye on these</h2><p>Budget alerts for your selected month.</p></div><span className="neutral-badge">{alerts.length} {alerts.length === 1 ? 'alert' : 'alerts'}</span></div>
    <div className="home-alert-grid">{alerts.map(row => {
      const over = row.status === 'over_budget'
      return <article className={`home-budget-alert ${over ? 'over-budget' : 'at-risk'}`} key={row.category}>
        <Icon name="alert" /><div><div className="home-alert-heading"><strong>{row.category}</strong><span className={`status-pill ${row.status}`}>{over ? 'Over budget' : 'At risk'}</span></div>
          <p>{over ? `You are INR ${formatMoney(Number(row.spent_so_far) - Number(row.monthly_limit))} over your budget.` : `Projected spending is INR ${formatMoney(row.projected_spend)} against a budget of INR ${formatMoney(row.monthly_limit)}.`}</p>
          <small>Spent INR {formatMoney(row.spent_so_far)} · Budget INR {formatMoney(row.monthly_limit)}</small>
        </div>
      </article>
    })}</div>
  </section>
}
