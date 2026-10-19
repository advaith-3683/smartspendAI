import React from 'react'

// Same currentColor line-SVG convention as the project's category icon set.
const paths = {
  menu: 'M4 6h16M4 12h16M4 18h16',
  close: 'm6 6 12 12M18 6 6 18',
  right: 'm9 5 7 7-7 7',
  logout: 'M9 4H4v16h5M13 12h9m-4-4 4 4-4 4',
  shield: 'm12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Zm-4 9 3 3 5-6',
  import: 'M12 3v12m-4-4 4 4 4-4M4 15v6h16v-6',
  calendar: 'M4 5h16v16H4ZM8 3v4M16 3v4M4 10h16',
  overview: 'M3 10 12 3l9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z',
  transactions: 'M4 7h16M16 3l4 4-4 4M20 17H4m4-4-4 4 4 4',
  budgets: 'M3 7h18v13H3zM3 7V4h15v3M15 12h6v4h-6z',
  planning: 'M12 3a9 9 0 1 0 9 9M12 7a5 5 0 1 0 5 5M12 12l9-9m-5 0h5v5',
  coach: 'M21 11a8 8 0 0 1-8 8H8l-5 3V11a9 9 0 0 1 18 0ZM8 10h.01M12 10h.01M16 10h.01',
  settings: 'M20 21v-2a6 6 0 0 0-6-6h-4a6 6 0 0 0-6 6v2M16 6a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z',
  microphone: 'M9 4a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0ZM5 10v1a7 7 0 0 0 14 0v-1M12 18v4m-4 0h8',
  audio: 'M11 4 6 9H2v6h4l5 5ZM15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14',
  eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12ZM15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
  plus: 'M12 5v14M5 12h14',
  alert: 'M12 3 2 21h20ZM12 9v5m0 3h.01',
  refresh: 'M20 7v5h-5M4 17v-5h5M6 6a8 8 0 0 1 14 6M4 12a8 8 0 0 0 14 6',
}
export default function Icon({ name, ...props }) {
  return <svg className="ui-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}><path d={paths[name] || paths.budgets} /></svg>
}
