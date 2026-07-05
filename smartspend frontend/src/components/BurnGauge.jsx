import React from 'react'
import { getStatusColors } from '../statusColors.js'

// Full 360-degree gradient ring with a soft outer glow. Categories that
// aren't safely on-track get a slow pulsing halo to draw the eye.
export default function BurnGauge({ percent, status, size = 120 }) {
  const fillFraction = Math.min(Math.max(percent, 0), 100) / 100
  const strokeWidth = 8
  const r = size / 2 - strokeWidth - 4
  const circumference = 2 * Math.PI * r
  const offset = circumference * (1 - fillFraction)
  const colors = getStatusColors(status)
  const uid = `${status}-${Math.round(percent)}`
  const gradId = `gauge-gradient-${uid}`
  const glowId = `gauge-blur-${uid}`
  const shouldPulse = status !== 'on_track'

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ overflow: 'visible' }}>
      <defs>
        <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor={colors.bright} />
          <stop offset="100%" stopColor={colors.solid} />
        </linearGradient>
        <filter id={glowId} x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="4" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {shouldPulse && (
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={colors.solid}
          strokeWidth={strokeWidth + 6}
          opacity="0.25"
          className="gauge-pulse-ring"
        />
      )}

      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="rgba(255,255,255,0.06)"
        strokeWidth={strokeWidth}
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={`url(#${gradId})`}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        filter={`url(#${glowId})`}
        style={{ transition: 'stroke-dashoffset 0.4s ease' }}
      />
    </svg>
  )
}
