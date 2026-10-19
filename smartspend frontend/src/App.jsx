import React, { useEffect, useState, useCallback, useRef } from 'react'
import { api } from './api.js'
import AuthScreen from './components/AuthScreen.jsx'
import Icon from './components/Icon.jsx'
import { Notice } from './components/design/Notice.jsx'
import WorkspaceShell from './components/WorkspaceShell.jsx'
import Overview from './components/Overview.jsx'
import EmailEnrollment from './components/EmailEnrollment.jsx'
import { ConfirmProvider } from './components/ConfirmDialog.jsx'
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
import SubscriptionsPanel from './components/SubscriptionsPanel.jsx'

const now = new Date()
const TODAY_YEAR = now.getFullYear()
const TODAY_MONTH = now.getMonth() + 1

function Profile({ user, onSaved }) {
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const busy = useRef(false)
  const [name, setName] = useState(user.name)
  const [income, setIncome] = useState(user.monthly_income)
  const [saving, setSaving] = useState(false)
  return <div className="card profile-editor"><h2>Profile details</h2><p className="period-note">{user.email || 'Email not added yet'}{user.email && ' ? Ownership not verified'}</p><p className="period-note">Keep your name and monthly income up to date.</p><form onSubmit={async e => {
    e.preventDefault(); if (busy.current) return; busy.current = true; setSaving(true); setSaved(false); setError('')
    try { onSaved(await api.updateProfile({ name: name.trim(), monthly_income: Number(income) })); setSaved(true) }
    catch (err) { setError(err.message) } finally { busy.current = false; setSaving(false) }
  }}><label>Name <input required maxLength={100} value={name} onChange={e => setName(e.target.value)} /></label>
    <label>Monthly income (INR) <input type="number" required min="0" step="0.01" value={income} onChange={e => setIncome(e.target.value)} /></label>
    <button className="btn" disabled={saving}>Save profile</button>{saved && <p role="status" className="success-text">Profile saved.</p>}{error && <p role="alert" className="error-text">{error}</p>}
  </form></div>
}

export default function App() {
  const refreshVersion = useRef(0)
  const currentPeriod = useRef('')
  const [user, setUser] = useState(null)
  const [checkingUser, setCheckingUser] = useState(true)
  const [pace, setPace] = useState([])
  const [transactions, setTransactions] = useState([])
  const [anomalies, setAnomalies] = useState([])
  const [loadError, setLoadError] = useState('')
  const [selectedYear, setSelectedYear] = useState(TODAY_YEAR)
  const [activeView, setActiveView] = useState('overview')
  const [loadingData, setLoadingData] = useState(false)
  const [upcomingBills, setUpcomingBills] = useState([])
  const [selectedMonth, setSelectedMonth] = useState(TODAY_MONTH)

  const [hasLoaded, setHasLoaded] = useState(false)
  const logoutBusy = useRef(false)
  const [loggingOut, setLoggingOut] = useState(false)
  const [retryingSession, setRetryingSession] = useState(false)
  const [transactionView, setTransactionView] = useState('ledger')
  const addTransaction = () => { setActiveView('transactions'); setTransactionView('entry') }
  useEffect(() => { if (activeView === 'transactions' && transactionView === 'entry') document.getElementById('txn-amount')?.focus() }, [activeView, transactionView])
  const retrySession = async () => {
    if (retryingSession) return
    setRetryingSession(true); setLoadError('')
    try { setUser(await api.me()) } catch (err) { if (err.status !== 401) setLoadError(err.message) }
    finally { setRetryingSession(false) }
  }
  const logout = async () => {
    if (logoutBusy.current) return
    logoutBusy.current = true; setLoggingOut(true)
    try { await api.logout(); window.dispatchEvent(new Event('smartspend:logout')) }
    catch (err) { setLoadError(err.message) }
    finally { logoutBusy.current = false; setLoggingOut(false) }
  }

  useEffect(() => {
    try { localStorage.removeItem('smartspend_user_id') } catch { /* Storage may be disabled; authentication uses cookies. */ }
    const clear = event => { api.resetSession(); refreshVersion.current += 1; setUser(null); setTransactions([]); setPace([]); setAnomalies([]); setUpcomingBills([]); setLoadError(event?.detail?.expired ? 'Your session expired. Log in again to continue. Your saved records are safe.' : ''); setActiveView('overview'); setLoadingData(false); setHasLoaded(false) }
    window.addEventListener('smartspend:logout', clear)
    let mounted = true
    api.me().then(value => { if (mounted) setUser(value) }).catch(err => { if (mounted && err.status !== 401) setLoadError(err.message) }).finally(() => { if (mounted) setCheckingUser(false) })
    return () => { mounted = false; api.resetSession(); window.removeEventListener('smartspend:logout', clear) }
  }, [])

  currentPeriod.current = `${user?.id}-${selectedYear}-${selectedMonth}`
  const refreshData = useCallback(() => {
    if (!user || currentPeriod.current !== `${user.id}-${selectedYear}-${selectedMonth}`) return
    const version = ++refreshVersion.current
    setLoadError('')
    setLoadingData(true)
    Promise.all([
      api.getPaceAll(user.id, selectedYear, selectedMonth),
      api.listTransactions(user.id, selectedYear, selectedMonth),
      api.getAnomalies(user.id, selectedYear, selectedMonth),
      api.upcomingBills(user.id),
    ]).then(([nextPace, nextTransactions, nextAnomalies, nextBills]) => {
      if (version !== refreshVersion.current || currentPeriod.current !== `${user.id}-${selectedYear}-${selectedMonth}`) return
      setHasLoaded(true); setPace(nextPace); setTransactions(nextTransactions); setAnomalies(nextAnomalies); setUpcomingBills(nextBills.filter(b => b.status !== 'paid'))
    }).catch(err => { if (version === refreshVersion.current && currentPeriod.current === `${user.id}-${selectedYear}-${selectedMonth}`) setLoadError(err.message) }).finally(() => { if (version === refreshVersion.current && currentPeriod.current === `${user.id}-${selectedYear}-${selectedMonth}`) setLoadingData(false) })
  }, [user, selectedYear, selectedMonth])

  useEffect(() => {
    refreshData()
  }, [refreshData])

  useEffect(() => {
    if (!user) return
    let live = true
    const checkSession = () => api.me().then(next => {
      if (!live) return
      if (next.id !== user.id) {
        api.resetSession(); refreshVersion.current += 1
        setHasLoaded(false); setPace([]); setTransactions([]); setAnomalies([]); setUpcomingBills([])
        setActiveView('overview'); setLoadError(''); setUser(next)
      }
    }).catch(err => { if (live && err.status !== 401) setLoadError(err.message) })
    window.addEventListener('focus', checkSession)
    return () => { live = false; window.removeEventListener('focus', checkSession) }
  }, [user?.id])

  if (checkingUser) return <main className="session-loading" role="status"><span className="brand-mark"><Icon name="budgets" /></span><h1>SmartSpend</h1><span className="spinner" /><p>Restoring your account...</p></main>
  if (!user) return <AuthScreen sessionError={loadError} onRetrySession={retrySession} retryingSession={retryingSession} onCreated={value => { api.resetSession(); setLoadError(''); setUser(value) }} />

  const categories = pace.map(p => p.category)
  const unbudgeted = [...new Set(transactions.filter(t => !categories.includes(t.category)).map(t => t.category))]
  const selectView = view => { if (view === 'transactions') setTransactionView('ledger'); setActiveView(view) }
  const descriptions = {
    overview: 'A little clarity for your day. Here is where your money stands.',
    transactions: 'Keep your everyday spending organised, one entry at a time.',
    budgets: 'Set practical limits and keep recurring payments in view.',
    planning: 'Find the patterns and practical next steps behind your spending.',
    coach: 'Think through your money questions with Coco. You decide what gets saved.',
    settings: 'A few details to make your workspace feel like yours.',
  }
  return <ConfirmProvider key={user.id}><WorkspaceShell user={user} activeView={activeView} onSelect={selectView} onLogout={logout} loggingOut={loggingOut}>
    <main className="app-shell" id="main-content" tabIndex={-1}>
      <header className="ledger-header"><div><div className="section-eyebrow">YOUR MONEY, CONNECTED</div><h1>{({ overview: `Your overview, ${user.name.split(' ')[0]}`, transactions: 'Transactions', budgets: 'Budgets & bills', planning: 'Goals & insights', coach: 'Your space with Coco', settings: 'Your account' })[activeView]}</h1><p className="header-subtitle">{descriptions[activeView]}</p></div>{['overview', 'transactions'].includes(activeView) && <button className="btn" onClick={addTransaction}><Icon name="plus" />Add transaction</button>}</header>
      {activeView !== 'settings' && <div className="period-toolbar"><div><span className="toolbar-label">Selected period</span><MonthNav year={selectedYear} month={selectedMonth} onChange={(y, m) => { refreshVersion.current += 1; setHasLoaded(false); setPace([]); setTransactions([]); setAnomalies([]); setUpcomingBills([]); setSelectedYear(y); setSelectedMonth(m) }} /></div><button className="btn secondary" onClick={refreshData} type="button" disabled={loadingData}><Icon name="refresh" />{loadingData ? 'Refreshing...' : 'Refresh'}</button></div>}
      {loadError && <Notice title="Unable to refresh your records" action={<button className="text-button" onClick={refreshData}>Retry</button>}><p>{loadError}</p></Notice>}
      {loadingData && activeView !== 'overview' && <p className="loading-records" role="status"><span className="spinner" />Loading your saved records...</p>}
      {activeView === 'overview' && <Overview user={user} pace={pace} transactions={transactions} bills={upcomingBills} loaded={hasLoaded} loading={loadingData} error={loadError} onSelect={selectView} onAdd={addTransaction} />}

      <div hidden={activeView !== 'transactions'} className="page-sections">
        <nav className="page-tabs" aria-label="Transaction workspace">{[['ledger', 'Your ledger'], ['entry', 'Add expense'], ['import', 'Import transactions']].map(([id, label]) => <button key={id} type="button" aria-pressed={transactionView === id} className={transactionView === id ? 'active' : ''} onClick={() => setTransactionView(id)}>{label}</button>)}</nav>
        <section hidden={transactionView !== 'ledger'}><div className="section-heading"><span className="section-icon"><Icon name="transactions" /></span><div><h2>Your transactions</h2><p>Search, filter and update the selected month.</p></div></div>{hasLoaded ? <TransactionList key={`${user.id}-${selectedYear}-${selectedMonth}`} transactions={transactions} onEdit={(id, data) => api.updateTransaction(id, { ...data, user_id: user.id }).then(refreshData)} onDelete={id => api.deleteTransaction(id).then(refreshData)} /> : <div className="empty-note">{loadError ? 'Your ledger could not be loaded. Use Retry above.' : 'Loading your saved ledger...'}</div>}</section>
        <section hidden={transactionView !== 'entry'} className="form-layout"><div className="form-description"><span className="section-icon"><Icon name="plus" /></span><h2>Add an expense</h2><p>Record what you spent. Choose a category and the date it happened.</p><small>The selected period sets the default date. You can change it before saving.</small></div><TransactionForm key={`${user.id}-${selectedYear}-${selectedMonth}`} categories={categories} year={selectedYear} month={selectedMonth} onSubmit={data => api.createTransaction({ user_id: user.id, ...data }).then(refreshData)} /></section>
        <section hidden={transactionView !== 'import'} className="form-layout"><div className="form-description"><span className="section-icon"><Icon name="import" /></span><h2>Bring your spending together</h2><p>Paste bank messages or upload a CSV or PDF statement.</p><small>Review and edit every selected debit before importing. A preview does not save transactions.</small></div><ImportPanel userId={user.id} onImported={refreshData} /></section>
      </div>

      <div hidden={activeView !== 'budgets'} className="page-sections">
        <section><div className="section-heading"><span className="section-icon"><Icon name="budgets" /></span><div><h2>Your category budgets</h2><p>Actual spending and projected pace for the selected month.</p></div></div><BurnAlertBanner pace={pace} />{!hasLoaded ? <div className="empty-note">{loadError ? 'Budget information is unavailable.' : 'Loading saved budgets...'}</div> : pace.length ? <div className="budget-grid">{pace.map(p => <BudgetCard key={p.category} pace={p} />)}</div> : <div className="empty-note"><h3>Give your month a plan</h3><p>Add your first category budget below.</p></div>}</section>
        <section className="form-layout"><div className="form-description"><span className="section-icon"><Icon name="planning" /></span><h2>Set a category budget</h2><p>Choose a monthly limit. Saving an existing category updates that month's budget.</p></div><BudgetForm key={`${user.id}-${selectedYear}-${selectedMonth}`} onSubmit={data => api.createBudget({ user_id: user.id, year: selectedYear, month: selectedMonth, ...data }).then(refreshData)} /></section>
        <section><div className="section-heading"><span className="section-icon"><Icon name="calendar" /></span><div><h2>Recurring bills</h2><p>Keep due dates, paid status and payment expenses together.</p></div></div><BillsPanel key={`${user.id}-${selectedYear}-${selectedMonth}`} userId={user.id} year={selectedYear} month={selectedMonth} onChange={refreshData} /></section>
      </div>

      <div hidden={activeView !== 'planning'} className="page-sections">
        <section className="card"><div className="section-heading"><span className="section-icon"><Icon name="planning" /></span><div><h2>Spending patterns</h2><p>Unusual activity for the selected month.</p></div></div>{!hasLoaded ? <p className="period-note">{loadError ? 'Insights are unavailable.' : 'Loading insights...'}</p> : anomalies.length ? <AnomalyBanner anomalies={anomalies} /> : <div className="empty-note">No unusual spending patterns detected for the selected month.</div>}</section>
        <div className="planning-grid"><section><div className="section-heading"><span className="section-icon"><Icon name="planning" /></span><div><h2>Plan a savings goal</h2><p>Find a practical path based on your saved history.</p></div></div><SavingsGoalPlanner userId={user.id} /></section><section><div className="section-heading"><span className="section-icon"><Icon name="budgets" /></span><div><h2>Should I buy this?</h2><p>Check the impact before you decide.</p></div></div><BuyDecision userId={user.id} categories={[...categories, ...unbudgeted]} year={selectedYear} month={selectedMonth} /></section></div>
        <section className="card"><div className="section-heading"><span className="section-icon"><Icon name="calendar" /></span><div><h2>Recurring subscriptions</h2><p>Patterns detected from your saved merchant history.</p></div></div><SubscriptionsPanel transactions={transactions} userId={user.id} /></section>
        <section className="card"><div className="section-heading"><span className="section-icon"><Icon name="coach" /></span><div><h2>Your weekly check-in</h2><p>Review the week and choose your next step.</p></div></div><WeeklyDigest userId={user.id} /></section>
      </div>

      <section hidden={activeView !== 'coach'} className="coco-page"><CoachPanel active={activeView === 'coach'} userId={user.id} year={selectedYear} month={selectedMonth} onExpenseLogged={refreshData} /></section>
      <section hidden={activeView !== 'settings'} className="form-layout account-section"><div className="form-description"><span className="section-icon"><Icon name="settings" /></span><h2>Your profile</h2><p>Your monthly income helps put spending in context.</p><div className="account-session"><h3>Ready to step away?</h3><p>Logging out ends this session. Your saved records stay in your account.</p><button className="btn secondary" disabled={loggingOut} onClick={logout}>Log out of this session</button></div></div><div className="page-sections"><Profile user={user} onSaved={setUser} /><EmailEnrollment user={user} onSaved={setUser} /></div></section>
    </main>
  </WorkspaceShell></ConfirmProvider>
}
