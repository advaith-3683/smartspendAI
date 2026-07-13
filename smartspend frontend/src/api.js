const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(detail.detail || `Request failed: ${res.status}`)
  }
  return res.json()
}

export const api = {
  createUser: (data) => request('/users', { method: 'POST', body: JSON.stringify(data) }),
  getUser: (id) => request(`/users/${id}`),

  createBudget: (data) => request('/budgets', { method: 'POST', body: JSON.stringify(data) }),
  listBudgets: (userId, year, month) =>
    request(`/budgets/${userId}?year=${year}&month=${month}`),

  createTransaction: (data) => request('/transactions', { method: 'POST', body: JSON.stringify(data) }),
  listTransactions: (userId, year, month) =>
    request(`/transactions/${userId}?year=${year}&month=${month}`),
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
    const res = await fetch(`${BASE_URL}/ingest/statement`, { method: 'POST', body: formData })
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}))
      throw new Error(detail.detail || `Request failed: ${res.status}`)
    }
    return res.json()
  },

  commitIngest: (userId, transactions) =>
    request('/ingest/commit', {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, transactions }),
    }),

  createBill: (data) => request('/bills', { method: 'POST', body: JSON.stringify(data) }),
  listBills: (userId, year, month) => request(`/bills/${userId}?year=${year}&month=${month}`),
  payBill: (billId, year, month) =>
    request(`/bills/${billId}/pay?year=${year}&month=${month}`, { method: 'POST' }),
  unpayBill: (billId, year, month) =>
    request(`/bills/${billId}/unpay?year=${year}&month=${month}`, { method: 'POST' }),
  deleteBill: (billId) => request(`/bills/${billId}`, { method: 'DELETE' }),
}
