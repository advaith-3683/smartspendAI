import React from 'react'

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

export default function MonthNav({ year, month, onChange }) {
  const goPrev = () => {
    if (month === 1) onChange(year - 1, 12)
    else onChange(year, month - 1)
  }
  const goNext = () => {
    if (month === 12) onChange(year + 1, 1)
    else onChange(year, month + 1)
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <button className="btn secondary" type="button" onClick={goPrev} aria-label="Previous month">
        ‹
      </button>
      <div className="month-label" style={{ minWidth: 130, textAlign: 'center' }}>
        {MONTH_NAMES[month - 1]} {year}
      </div>
      <button className="btn secondary" type="button" onClick={goNext} aria-label="Next month">
        ›
      </button>
    </div>
  )
}
