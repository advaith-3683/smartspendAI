import React from 'react'
import { formatMoney as money } from '../money.js'
import { getCategoryIcon } from '../categoryIcons.jsx'
const labels = { on_track: 'On track', at_risk: 'At risk', over_budget: 'Over budget' }
export default function BudgetCard({ pace }) {
  const CategoryIcon = getCategoryIcon(pace.category)
  return <article className="card budget-card">
    <div className="budget-card-heading"><span className="section-icon"><CategoryIcon width="22" height="22" /></span><strong>{pace.category}</strong><span className={`status-pill ${pace.status}`}>{labels[pace.status]}</span></div>
    <div className="budget-amount">INR {money(pace.spent_so_far)}</div><p className="budget-limit">spent of INR {money(pace.monthly_limit)}</p>
    <progress value={Math.min(pace.spent_so_far, pace.monthly_limit)} max={pace.monthly_limit} aria-label={`${pace.category}: INR ${money(pace.spent_so_far)} spent of INR ${money(pace.monthly_limit)}`} />
    <div className="budget-projection"><span>Projected spending</span><strong>INR {money(pace.projected_spend)}</strong></div><p className="period-note">{Math.round(pace.percent_of_budget_projected)}% of budget projected ? Day {pace.days_elapsed} of {pace.days_in_month}</p>
  </article>
}
