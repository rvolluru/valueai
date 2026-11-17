import React from 'react'
import { createRoot } from 'react-dom/client'
import { ClerkProvider } from '@clerk/clerk-react'
import App from './App'
import './styles.css'

const clerkPublishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY
const publicSupportPage = window.location.pathname.replace(/\/$/, '') === '/support'

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {clerkPublishableKey && !publicSupportPage ? (
      <ClerkProvider publishableKey={clerkPublishableKey}>
        <App />
      </ClerkProvider>
    ) : (
      <App />
    )}
  </React.StrictMode>,
)
