import React, { useEffect, useState, useCallback } from 'react'
import { api } from './api.js'
import BudgetCard from './components/BudgetCard.jsx'
import BudgetForm from './components/BudgetForm.jsx'
import TransactionForm from './components/TransactionForm.jsx'
import TransactionList from './components/TransactionList.jsx'
import BuyDecision from './components/BuyDecision.jsx'
import CoachPanel from './components/CoachPanel.jsx'
import AnomalyBanner from './components/AnomalyBanner.jsx'
import BurnAlertBanner from './components/BurnAlertBanner.jsx'
import MonthNav from './components/MonthNav.jsx'
import ImportPanel from './components/ImportPanel.jsx'
import BillsPanel from './components/BillsPanel.jsx'
import SavingsGoalPlanner from './components/SavingsGoalPlanner.jsx'
import WeeklyDigest from './components/WeeklyDigest.jsx'

const now = new Date()
const TODAY_YEAR = now.getFullYear()
const TODAY_MONTH = now.getMonth() + 1

function Onboarding({ onCreated }) {
  const [name, setName] = useState('')
  const [income, setIncome] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (!name.trim() || !income) {
      setError('Enter your name and monthly income.')
      return
    }
    setLoading(true)
    try {
      const user = await api.createUser({ name: name.trim(), monthly_income: parseFloat(income) })
      localStorage.setItem('smartspend_user_id', String(user.id))
      onCreated(user)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="onboard-wrap">
      <div className="card onboard-card">
        <div className="brand">Smart<span style={{ color: 'var(--gold)', fontStyle: 'italic' }}>Spend</span></div>
        <div className="tagline">AI FINANCIAL COACH — SET UP YOUR LEDGER</div>
        <form onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="onboard-name">Your name</label>
            <input id="onboard-name" type="text" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="onboard-income">Monthly income (₹)</label>
            <input
              id="onboard-income"
              type="number"
              value={income}
              onChange={(e) => setIncome(e.target.value)}
            />
          </div>
          <button className="btn" type="submit" disabled={loading}>
            {loading ? 'Setting up...' : 'Start budgeting'}
          </button>
        </form>
        {error && <div className="error-text">{error}</div>}
      </div>
    </div>
  )
}

export default function App() {
  const [user, setUser] = useState(null)
  const [checkingUser, setCheckingUser] = useState(true)
  const [pace, setPace] = useState([])
  const [transactions, setTransactions] = useState([])
  const [anomalies, setAnomalies] = useState([])
  const [loadError, setLoadError] = useState('')
  const [selectedYear, setSelectedYear] = useState(TODAY_YEAR)
  const [selectedMonth, setSelectedMonth] = useState(TODAY_MONTH)

  useEffect(() => {
    const storedId = localStorage.getItem('smartspend_user_id')
    if (!storedId) {
      setCheckingUser(false)
      return
    }
    api
      .getUser(parseInt(storedId, 10))
      .then((u) => setUser(u))
      .catch(() => localStorage.removeItem('smartspend_user_id'))
      .finally(() => setCheckingUser(false))
  }, [])

  const refreshData = useCallback(() => {
    if (!user) return
    api
      .getPaceAll(user.id, selectedYear, selectedMonth)
      .then(setPace)
      .catch((err) => setLoadError(err.message))
    api
      .listTransactions(user.id, selectedYear, selectedMonth)
      .then(setTransactions)
      .catch((err) => setLoadError(err.message))
    api
      .getAnomalies(user.id, selectedYear, selectedMonth)
      .then(setAnomalies)
      .catch(() => {}) // non-critical, fail silently
  }, [user, selectedYear, selectedMonth])

  useEffect(() => {
    refreshData()
  }, [refreshData])

  if (checkingUser) return null
  if (!user) return <Onboarding onCreated={setUser} />

  const categories = pace.map((p) => p.category)
  const totalSpent = pace.reduce((sum, p) => sum + p.spent_so_far, 0)

  return (
    <div className="app-shell">
      <header className="ledger-header">
        <div className="brand">
          Smart<span className="accent">Spend</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <MonthNav
            year={selectedYear}
            month={selectedMonth}
            onChange={(y, m) => { setSelectedYear(y); setSelectedMonth(m) }}
          />
          <button className="btn secondary" onClick={refreshData} type="button">
            ↻ Refresh
          </button>
        </div>
      </header>

      <div className="income-strip">
        <div>MONTHLY INCOME<strong>₹{user.monthly_income.toLocaleString('en-IN')}</strong></div>
        <div>SPENT SO FAR<strong>₹{totalSpent.toLocaleString('en-IN')}</strong></div>
        <div>REMAINING<strong>₹{(user.monthly_income - totalSpent).toLocaleString('en-IN')}</strong></div>
      </div>

      {loadError && <div className="error-text" style={{ marginBottom: 20 }}>{loadError}</div>}

      <BurnAlertBanner pace={pace} />
      <AnomalyBanner anomalies={anomalies} />

      <section className="block">
        <div className="section-eyebrow">Burn rate</div>
        <div className="section-title">Category pace tracking</div>
        {pace.length === 0 ? (
          <div className="empty-note">No budgets set for this month yet. Add one below.</div>
        ) : (
          <div className="budget-grid">
            {pace.map((p) => (
              <BudgetCard key={p.category} pace={p} />
            ))}
          </div>
        )}
      </section>

      <section className="block">
        <div className="section-eyebrow">Setup</div>
        <div className="section-title">Set a category budget</div>
        <BudgetForm
          onSubmit={(data) =>
            api
              .createBudget({ user_id: user.id, year: selectedYear, month: selectedMonth, ...data })
              .then(refreshData)
          }
        />
      </section>

      <section className="block">
        <div className="section-eyebrow">Recurring</div>
        <div className="section-title">Monthly bills</div>
        <BillsPanel userId={user.id} year={selectedYear} month={selectedMonth} onChange={refreshData} />
      </section>

      <section className="block">
        <div className="section-eyebrow">Log</div>
        <div className="section-title">Add an expense</div>
        <TransactionForm
          categories={categories}
          year={selectedYear}
          month={selectedMonth}
          onSubmit={(data) => api.createTransaction({ user_id: user.id, ...data }).then(refreshData)}
        />
      </section>

      <section className="block">
        <div className="section-eyebrow">Automated ingestion</div>
        <div className="section-title">Import from SMS or bank statement</div>
        <ImportPanel userId={user.id} onImported={refreshData} />
      </section>

      <section className="block">
        <div className="section-eyebrow">Copilot</div>
        <div className="section-title">Should I buy this?</div>
        <BuyDecision userId={user.id} categories={categories} />
      </section>

      <section className="block">
        <div className="section-eyebrow">Goals</div>
        <div className="section-title">Plan a savings goal</div>
        <SavingsGoalPlanner userId={user.id} />
      </section>

      <section className="block">
        <div className="section-eyebrow">COCO AI</div>
        <div className="section-title">Chat live with your money coach</div>
        <CoachPanel userId={user.id} year={selectedYear} month={selectedMonth} onExpenseLogged={refreshData} />
      </section>

      <section className="block">
        <div className="section-eyebrow">COCO AI</div>
        <div className="section-title">Your weekly check-in</div>
        <WeeklyDigest userId={user.id} />
      </section>

      <section className="block">
        <div className="section-eyebrow">Ledger</div>
        <div className="section-title">Recent transactions</div>
        <TransactionList
          transactions={transactions}
          onDelete={(id) => api.deleteTransaction(id).then(refreshData)}
        />
      </section>
    </div>
  )
}
