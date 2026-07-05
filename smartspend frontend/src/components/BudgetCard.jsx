import React from 'react'
import BurnGauge from './BurnGauge.jsx'
import { getCategoryIcon, getCategoryTint } from '../categoryIcons.jsx'
import { getStatusColors } from '../statusColors.js'

const STATUS_LABEL = {
  on_track: 'On track',
  at_risk: 'At risk',
  over_budget: 'Over budget',
}

export default function BudgetCard({ pace }) {
  const Icon = getCategoryIcon(pace.category)
  const tint = getCategoryTint(pace.category)
  const colors = getStatusColors(pace.status)

  return (
    <div className="card budget-card" style={{ '--card-glow': colors.glow }}>
      <div className="card-corner corner-tl" style={{ '--corner-color': colors.solid }} />
      <div className="card-corner corner-br" style={{ '--corner-color': colors.solid }} />

      <div className="category-name">{pace.category}</div>
      <div className="gauge-stack">
        <BurnGauge percent={pace.percent_of_budget_projected} status={pace.status} />
        <div
          className="gauge-icon-badge"
          style={{
            background: `linear-gradient(145deg, ${tint}33, ${tint}11)`,
            color: tint,
            boxShadow: `0 0 16px -2px ${tint}88, inset 0 0 0 1px ${tint}55`,
          }}
        >
          <Icon />
        </div>
      </div>
      <div className="gauge-percent" style={{ textShadow: `0 0 18px ${colors.glow}` }}>
        {Math.round(pace.percent_of_budget_projected)}%
      </div>
      <div className="gauge-percent-label">Projected</div>
      <span className={`status-pill ${pace.status}`}>{STATUS_LABEL[pace.status]}</span>
      <div className="figures">
        <div>
          <span className="spent">₹{pace.spent_so_far.toLocaleString('en-IN')}</span> / ₹
          {pace.monthly_limit.toLocaleString('en-IN')}
        </div>
        <div>
          Day {pace.days_elapsed} of {pace.days_in_month} · projected ₹
          {pace.projected_spend.toLocaleString('en-IN')}
        </div>
      </div>
    </div>
  )
}
