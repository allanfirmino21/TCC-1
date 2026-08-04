import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Fontes self-hosted (funcionam sem internet na demo)
import '@fontsource-variable/inter'
import '@fontsource-variable/fraunces'
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
