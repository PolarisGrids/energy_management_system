import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
// smoc-samples.css is served from /public and linked in index.html so the
// Tailwind v4 Vite plugin doesn't attempt to parse its sample-palette rules.
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
