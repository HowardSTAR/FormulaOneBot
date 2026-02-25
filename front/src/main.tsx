import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { initTelegram } from './helpers/telegram'
import App from './App.tsx'

initTelegram()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
