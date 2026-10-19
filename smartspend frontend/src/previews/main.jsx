import React from 'react'
import { createRoot } from 'react-dom/client'
import LoginPreviews from './LoginPreviews.jsx'

createRoot(document.getElementById('preview-root')).render(<React.StrictMode><LoginPreviews variant={document.documentElement.dataset.design} /></React.StrictMode>)
