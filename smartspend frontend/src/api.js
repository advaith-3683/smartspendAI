const BASE_URL = (import.meta.env.VITE_API_URL || (import.meta.env.DEV ? 'http://localhost:8000' : 'https://smartspend-backend-lsk5.onrender.com')).replace(/\/+$/, '')
let sessionVersion = 0
const pending = new Set()

function resetSession() {
  sessionVersion += 1
  for (const controller of pending) controller.abort()
  pending.clear()
}


async function request(path, options = {}) {
  const version = sessionVersion
  const controller = new AbortController()
  pending.add(controller)
  const timeout = setTimeout(() => controller.abort(), 60000)
  try {
    const isUpload = typeof FormData !== 'undefined' && options.body instanceof FormData
    const res = await fetch(`${BASE_URL}${path}`, {
      ...options,
      credentials: 'include',
      signal: controller.signal,
      headers: { ...(!isUpload && options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
    })
    if (version !== sessionVersion) throw new Error('Account changed. Please retry.')
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}))
      if (version !== sessionVersion) throw new Error('Account changed. Please retry.')
      if (res.status === 401 && !['/auth/login', '/auth/signup', '/auth/legacy-login'].includes(path)) window.dispatchEvent(new CustomEvent('smartspend:logout', { detail: { expired: path !== '/auth/me' } }))
      const message = Array.isArray(detail.detail) ? detail.detail.map(e => e.msg).join('; ') : detail.detail
      const error = new Error(res.status >= 500 ? `SmartSpend is temporarily unavailable (HTTP ${res.status}). Please retry shortly.` : typeof message === 'string' ? message : `Request failed: ${res.status}. Please retry.`)
      error.status = res.status
      throw error
    }
    if (res.status === 204) return null
    const data = await res.json().catch(() => { throw new Error('Unexpected server response. Refresh your saved records before retrying a save.') })
    if (version !== sessionVersion) throw new Error('Account changed. Please retry.')
    return data
  } catch (err) {
    if (err.status === 401) throw err
    if (version !== sessionVersion) throw new Error('Account changed. Please retry.')
    if (err instanceof TypeError) {
      const error = new Error('Cannot connect to SmartSpend. Retry shortly. If it continues, report the site address to support.')
      error.code = 'network'; throw error
    }
    if (controller.signal.aborted) { const error = new Error('SmartSpend took too long to respond. Retry in a moment. Check your ledger before retrying a save.'); error.code = 'timeout'; throw error }
    throw err
  } finally {
    pending.delete(controller)
    clearTimeout(timeout)
  }
}

export const api = {
  resetSession,
  signup: (data) => request('/auth/signup', { method: 'POST', body: JSON.stringify(data) }),
  login: (data) => request('/auth/login', { method: 'POST', body: JSON.stringify(data) }),
  legacyLogin: data => request('/auth/legacy-login', { method: 'POST', body: JSON.stringify(data) }),
  enrollEmail: data => request('/auth/enroll-email', { method: 'POST', body: JSON.stringify(data) }),
  me: () => request('/auth/me'),
  updateProfile: (data) => request('/auth/me', { method: 'PATCH', body: JSON.stringify(data) }),
  logout: () => request('/auth/logout', { method: 'POST' }),
  getUser: (id) => request(`/users/${id}`),

  createBudget: (data) => request('/budgets', { method: 'POST', body: JSON.stringify(data) }),
  listBudgets: (userId, year, month) =>
    request(`/budgets/${userId}?year=${year}&month=${month}`),

  createTransaction: (data) => request('/transactions', { method: 'POST', body: JSON.stringify(data) }),
  listTransactions: (userId, year, month) =>
    request(`/transactions/${userId}?year=${year}&month=${month}`),
  updateTransaction: (id, data) => request(`/transactions/item/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  getProposals: (id) => request(`/coach/proposals/${id}`),
  resolveProposal: (id, action) => request(`/coach/proposals/${id}/${action}`, { method: 'POST' }),
  deleteTransaction: (transactionId) =>
    request(`/transactions/item/${transactionId}`, { method: 'DELETE' }),

  getPaceAll: (userId, year, month) => request(`/pace/${userId}?year=${year}&month=${month}`),

  buyDecision: (data) => request('/buy-decision', { method: 'POST', body: JSON.stringify(data) }),

  getCoachAdvice: (userId, year, month) =>
    request(`/coach/${userId}${year && month ? `?year=${year}&month=${month}` : ''}`),
  getCoachHistory: (userId) => request(`/coach/history/${userId}`),
  clearCoachHistory: (userId) => request(`/coach/history/${userId}`, { method: 'DELETE' }),
  coachChat: (userId, message, year, month) =>
    request(`/coach/chat/${userId}${year && month ? `?year=${year}&month=${month}` : ''}`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),
  getAnomalies: (userId, year, month) => request(`/anomalies/${userId}?year=${year}&month=${month}`),
  getSubscriptions: (userId) => request(`/subscriptions/${userId}`),

  getSavingsGoalPlan: (userId, targetAmount, months) =>
    request(`/savings-goal/${userId}`, {
      method: 'POST',
      body: JSON.stringify({ target_amount: targetAmount, months }),
    }),

  getWeeklyDigest: (userId) => request(`/coach/digest/${userId}`),

  ingestSms: (userId, rawText) =>
    request('/ingest/sms', { method: 'POST', body: JSON.stringify({ user_id: userId, raw_text: rawText }) }),

  ingestStatement: async (file) => {
    const formData = new FormData()
    formData.append('file', file)
    return request('/ingest/statement', { method: 'POST', body: formData })
  },

  commitIngest: (userId, transactions, idempotencyKey) =>
    request('/ingest/commit', {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, transactions, idempotency_key: idempotencyKey }),
    }),

  createBill: (data) => request('/bills', { method: 'POST', body: JSON.stringify(data) }),
  upcomingBills: (userId) => request(`/bills/upcoming/${userId}`),
  listBills: (userId, year, month) => request(`/bills/${userId}?year=${year}&month=${month}`),
  payBill: (billId, year, month) =>
    request(`/bills/${billId}/pay?year=${year}&month=${month}`, { method: 'POST' }),
  unpayBill: (billId, year, month) =>
    request(`/bills/${billId}/unpay?year=${year}&month=${month}`, { method: 'POST' }),
  deleteBill: (billId) => request(`/bills/${billId}`, { method: 'DELETE' }),
}
