import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// Initialize retro-vintage dual theme (default to light mode)
const urlParams = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null
const queryTheme = urlParams ? urlParams.get('theme') : null
const savedTheme = queryTheme || (typeof window !== 'undefined' ? localStorage.getItem('monika_theme') : null)
const initialTheme = savedTheme === 'dark' ? 'dark' : 'light'
document.documentElement.setAttribute('data-theme', initialTheme)
if (queryTheme && typeof window !== 'undefined') {
  localStorage.setItem('monika_theme', queryTheme)
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
