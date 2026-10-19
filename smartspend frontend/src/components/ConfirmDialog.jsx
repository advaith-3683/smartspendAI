import React, { createContext, useContext, useEffect, useRef, useState } from 'react'

const ConfirmContext = createContext(null)
export const useConfirm = () => useContext(ConfirmContext)

export function ConfirmProvider({ children }) {
  const [message, setMessage] = useState('')
  const dialog = useRef(null)
  const resolver = useRef(null)
  const previousFocus = useRef(null)
  const cancelButton = useRef(null)
  const finish = value => {
    dialog.current?.close()
    resolver.current?.(value); resolver.current = null; setMessage('')
    previousFocus.current?.focus()
  }
  const confirm = text => {
    if (resolver.current) return Promise.resolve(false)
    previousFocus.current = document.activeElement
    return new Promise(resolve => { resolver.current = resolve; setMessage(text) })
  }
  useEffect(() => {
    if (message) { dialog.current?.showModal(); cancelButton.current?.focus() }
  }, [message])
  useEffect(() => () => resolver.current?.(false), [])
  return <ConfirmContext.Provider value={confirm}>{children}
    <dialog ref={dialog} className="confirm-dialog" aria-labelledby="confirm-title" aria-describedby="confirm-description" onCancel={event => { event.preventDefault(); finish(false) }}>
      <h2 id="confirm-title">Confirm this change</h2><p id="confirm-description">{message}</p>
      <div className="dialog-actions"><button ref={cancelButton} type="button" className="btn secondary" onClick={() => finish(false)}>Keep it</button><button type="button" className="btn" onClick={() => finish(true)}>Confirm</button></div>
    </dialog>
  </ConfirmContext.Provider>
}
