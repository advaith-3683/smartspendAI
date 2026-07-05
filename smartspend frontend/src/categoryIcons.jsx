import React from 'react'

// Minimal line-icon set, one per known category, drawn as plain SVG paths.
// currentColor is used so each icon inherits its badge's tint color.

const FoodIcon = (props) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" {...props}>
    <path d="M6 3v7a2 2 0 0 0 2 2v9M6 3v7M9 3v7M12 3v6a3 3 0 0 0 3 3v9M15 3c-1.5 1-2 3-2 5s1 3 2 3" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

const GroceriesIcon = (props) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" {...props}>
    <path d="M3 4h2l2.4 12.4a2 2 0 0 0 2 1.6h7.2a2 2 0 0 0 2-1.6L20 8H6" strokeLinecap="round" strokeLinejoin="round" />
    <circle cx="9.5" cy="20.5" r="1.2" />
    <circle cx="16.5" cy="20.5" r="1.2" />
  </svg>
)

const TransportIcon = (props) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" {...props}>
    <path d="M4 16V9a2 2 0 0 1 2-2h1l1.5-3h7L17 7h1a2 2 0 0 1 2 2v7" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M4 16h16M6 16v2M18 16v2" strokeLinecap="round" />
    <circle cx="7.5" cy="16" r="1.4" />
    <circle cx="16.5" cy="16" r="1.4" />
  </svg>
)

const ShoppingIcon = (props) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" {...props}>
    <path d="M6 8h12l-1 12a2 2 0 0 1-2 1.8H9A2 2 0 0 1 7 20L6 8Z" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M9 8V6a3 3 0 0 1 6 0v2" strokeLinecap="round" />
  </svg>
)

const EntertainmentIcon = (props) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" {...props}>
    <rect x="3" y="7" width="18" height="13" rx="1.5" />
    <path d="M3 10l3.5-4M9.5 10 13 6M16 10l3.5-4" strokeLinecap="round" />
  </svg>
)

const BillsIcon = (props) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" {...props}>
    <path d="M6 3h12v18l-2.5-1.5L13 21l-1.5-1.5L10 21l-2.5-1.5L5 21V3Z" strokeLinejoin="round" />
    <path d="M8 8h8M8 12h8M8 16h5" strokeLinecap="round" />
  </svg>
)

const HealthIcon = (props) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" {...props}>
    <path d="M20.5 8.5c0 4.5-8.5 10-8.5 10s-8.5-5.5-8.5-10a4.5 4.5 0 0 1 8.5-2 4.5 4.5 0 0 1 8.5 2Z" strokeLinejoin="round" />
    <path d="M6 11h2l1.5-2.5 2 5L13 11h5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

const MiscIcon = (props) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" {...props}>
    <rect x="4" y="4" width="7" height="7" rx="1" />
    <rect x="13" y="4" width="7" height="7" rx="1" />
    <rect x="4" y="13" width="7" height="7" rx="1" />
    <rect x="13" y="13" width="7" height="7" rx="1" />
  </svg>
)

const WalletIcon = (props) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" {...props}>
    <path d="M3 7a2 2 0 0 1 2-2h13a1 1 0 0 1 1 1v3" strokeLinecap="round" />
    <rect x="3" y="7" width="18" height="13" rx="2" />
    <circle cx="16.5" cy="13.5" r="1.4" />
  </svg>
)

export const CATEGORY_ICONS = {
  Food: FoodIcon,
  Groceries: GroceriesIcon,
  Transport: TransportIcon,
  Shopping: ShoppingIcon,
  Entertainment: EntertainmentIcon,
  Bills: BillsIcon,
  Health: HealthIcon,
  Miscellaneous: MiscIcon,
}

export const CATEGORY_TINTS = {
  Food: '#FF9F5A',
  Groceries: '#5AD1FF',
  Transport: '#9C8CFF',
  Shopping: '#5AFFC7',
  Entertainment: '#FF5AC7',
  Bills: '#FFD65A',
  Health: '#FF5A7A',
  Miscellaneous: '#9AA3B5',
}

export function getCategoryIcon(category) {
  return CATEGORY_ICONS[category] || WalletIcon
}

export function getCategoryTint(category) {
  return CATEGORY_TINTS[category] || '#9AA3B5'
}
