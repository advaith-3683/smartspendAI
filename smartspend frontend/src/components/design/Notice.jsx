import React from 'react'
import Icon from '../Icon.jsx'

export function Notice({ title, children, action, tone = 'error', className = '' }) {
  return <div className={`notice notice-${tone} ${className}`} role={tone === 'error' ? 'alert' : 'status'}><Icon name={tone === 'error' ? 'alert' : 'shield'} /><div className="notice-content">{title && <strong>{title}</strong>}{children}{action && <div className="notice-action">{action}</div>}</div></div>
}
