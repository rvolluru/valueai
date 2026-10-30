import { useEffect, useState } from 'react'
import { SignInButton, useAuth } from '@clerk/clerk-react'
import { documentFrameHtml } from '../lib/documentFrame.mjs'

export default function AnalysisGuidePage({ apiBaseUrl, document = 'listing-analysis' }) {
  const title = document === 'home' ? 'Jouft documentation' : document === 'system-architecture' ? 'System architecture' : 'Listing analysis guide'
  const { isLoaded, isSignedIn, getToken } = useAuth()
  const [html, setHtml] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    setHtml('')
    setError('')
    if (isLoaded && isSignedIn) {
      ;(async () => {
        try {
          const token = await getToken()
          const response = await fetch(`${apiBaseUrl.replace(/\/$/, '')}/v1/admin/docs/${document}`, {
            headers: { Authorization: `Bearer ${token}` }, cache: 'no-store', signal: controller.signal,
          })
          if (!response.ok) throw new Error(response.status === 403 ? 'This guide is available to administrators only.' : response.status === 401 ? 'Please sign in again to access this guide.' : 'Unable to load the guide.')
          const content = await response.text()
          if (!controller.signal.aborted) setHtml(documentFrameHtml(content))
        } catch (err) {
          if (!controller.signal.aborted) setError(err.message)
        }
      })()
    }
    return () => controller.abort()
  }, [isLoaded, isSignedIn, getToken, apiBaseUrl, document])
  if (!isLoaded) return <p role="status">Loading…</p>
  if (!isSignedIn) return <main className="panel"><h1>{title}</h1><p>Sign in with your administrator account.</p><SignInButton mode="modal"><button>Sign in</button></SignInButton></main>
  if (error) return <main className="panel"><h1>{title}</h1><p role="alert">{error}</p><a href="/">Back to Jouft</a></main>
  if (!html) return <p role="status">Loading guide…</p>
  return <iframe title="Jouft documentation" srcDoc={html} sandbox="allow-scripts allow-top-navigation-by-user-activation allow-popups allow-popups-to-escape-sandbox allow-modals" style={{ width: '100%', height: '100dvh', border: 0, display: 'block' }} />
}
