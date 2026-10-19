import React from 'react'
import { getStatusColors } from '../statusColors.js'

export default function BurnGauge({ percent, status, size = 120 }) {
  const fraction = Math.min(Math.max(percent, 0), 100) / 100
  const radius = size / 2 - 12
  const circumference = 2 * Math.PI * radius
  return <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${Math.round(percent)} percent of budget projected`}>
    <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--line)" strokeWidth="7" />
    <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={getStatusColors(status).solid} strokeWidth="7" strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={circumference * (1 - fraction)} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
  </svg>
}
