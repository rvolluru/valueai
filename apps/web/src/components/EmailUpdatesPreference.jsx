import { useCallback, useEffect, useMemo, useState } from 'react'
import { createWebApiClient } from '../lib/apiClient'

export default function EmailUpdatesPreference({ apiBaseUrl, apiKey, clerkEnabled, getBearerToken }) {
  const { client, authContext } = useMemo(() => createWebApiClient({ apiBaseUrl, apiKey: clerkEnabled ? '' : apiKey }), [apiBaseUrl, apiKey, clerkEnabled])
  const getAuth = useCallback(async () => authContext(clerkEnabled && getBearerToken ? await getBearerToken() : null), [authContext, clerkEnabled, getBearerToken])
  const [subscribed, setSubscribed] = useState(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const data = await client.get('/v1/me/email-updates', await getAuth())
        if (!cancelled) setSubscribed(data.subscribed)
      } catch { if (!cancelled) setMessage('Save your profile email first, or try again later.') }
    }
    void load()
    return () => { cancelled = true }
  }, [client, getAuth])
  async function update() {
    setBusy(true)
    setMessage('')
    try {
      const data = await client.put('/v1/me/email-updates', { subscribed: !subscribed }, await getAuth())
      setSubscribed(data.subscribed)
      setMessage(data.subscribed ? 'Email updates enabled.' : 'You are unsubscribed from email updates.')
    } catch { setMessage('Could not save your email preference. Please try again.') }
    finally { setBusy(false) }
  }
  return <section style={{ margin: '20px 0' }} aria-label="Email updates">
    <h3>Email updates</h3>
    <p>Receive a daily feed of new marketplace matches for your listings. No email is sent when there are no new matches.</p>
    {subscribed !== null && <button className="ghost small" type="button" disabled={busy} onClick={update}>
      {busy ? 'Saving…' : subscribed ? 'Unsubscribe from email updates' : 'Subscribe to email updates'}
    </button>}
    {message && <p role="status">{message}</p>}
  </section>
}
