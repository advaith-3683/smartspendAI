import React, { useEffect, useRef, useState } from 'react'
import Icon from './Icon.jsx'
import { Brand } from './design/Identity.jsx'

const sections = [['overview', 'Overview'], ['transactions', 'Transactions'], ['budgets', 'Budgets & bills'], ['planning', 'Goals & insights'], ['coach', 'Coco'], ['settings', 'Account']]

export default function WorkspaceShell({ user, activeView, onSelect, onLogout, loggingOut, children }) {
  const [open, setOpen] = useState(false)
  const drawer = useRef(null)
  const menuButton = useRef(null)
  const close = () => { setOpen(false); drawer.current?.close(); menuButton.current?.focus() }
  useEffect(() => {
    const media = window.matchMedia('(min-width: 1024px)')
    const changed = () => { if (media.matches) close() }
    media.addEventListener('change', changed)
    return () => media.removeEventListener('change', changed)
  }, [])
  const choose = section => { onSelect(section); close() }
  const navigation = mobile => <>
    <div className="shell-brand"><Brand />{mobile && <button className="icon-button" aria-label="Close navigation" onClick={close}><Icon name="close" /></button>}</div>
    <nav aria-label={mobile ? 'Mobile navigation' : 'Main navigation'}>{sections.map(([id, title]) => <button type="button" key={id} className={`nav-item ${activeView === id ? 'active' : ''}`} aria-current={activeView === id ? 'page' : undefined} onClick={() => choose(id)}><Icon name={id} /><span>{title}</span><Icon name="right" className="nav-chevron" /></button>)}</nav>
    <div className="sidebar-note"><Icon name="coach" /><strong>A little guidance from Coco</strong><p>Talk through your spending and review every expense before saving.</p><button type="button" className="text-button" onClick={() => choose('coach')}>Open Coco <Icon name="right" /></button></div>
    <div className="sidebar-account"><span className="avatar">{user.name.slice(0, 1).toUpperCase()}</span><span><strong>{user.name}</strong><small>Personal account</small></span><button type="button" className="icon-button" disabled={loggingOut} aria-label="Log out" title="Log out" onClick={onLogout}><Icon name="logout" /></button></div>
  </>
  return <div className="workspace"><a className="skip-link" href="#main-content">Skip to content</a>
    <aside className="desktop-sidebar">{navigation(false)}</aside>
    <dialog id="workspace-navigation" ref={drawer} className="navigation-drawer" aria-label="Workspace navigation" onClick={event => { if (event.target === drawer.current) close() }} onCancel={() => setOpen(false)}>{navigation(true)}</dialog>
    <div className="workspace-main"><header className="workspace-topbar"><button ref={menuButton} type="button" className="icon-button menu-button" aria-label="Open navigation" aria-haspopup="dialog" aria-controls="workspace-navigation" aria-expanded={open} onClick={() => { drawer.current?.showModal(); setOpen(true) }}><Icon name="menu" /></button><div className="workspace-breadcrumb"><span>Personal workspace</span><Icon name="right" /><strong>{sections.find(([id]) => id === activeView)?.[1]}</strong></div><button type="button" className="topbar-account" onClick={() => onSelect('settings')} aria-label="Open your account"><span className="avatar">{user.name.slice(0, 1).toUpperCase()}</span><span>{user.name}</span></button></header>
      {children}
      <footer className="workspace-footer"><span>SmartSpend AI · Personal workspace</span><span>Your finances, together.</span></footer>
    </div>
  </div>
}
