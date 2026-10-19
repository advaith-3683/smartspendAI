// API values are major INR units; formatting never converts them a second time.
export const formatMoney = value => Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
export const toMinor = value => Math.round(Number(value) * 100)
