import { useEffect, useMemo, useRef, useState } from 'react'
import { createWebApiClient } from '../lib/apiClient'
import { createListingAgentController } from '../../../../packages/app-client/src/listingAgent'

export default function ListingAgentChat({ apiBaseUrl, apiKey, getBearerToken, clerkEnabled }) {
  const [view, setView] = useState({ session: null, busy: false, error: '' })
  const [text, setText] = useState('')
  const [files, setFiles] = useState([])
  const auth = useRef(null)
  auth.current = async () => clerkEnabled ? { bearerToken: await getBearerToken() } : { apiKey }
  const { controller } = useMemo(() => {
    const { client } = createWebApiClient({ apiBaseUrl, apiKey, getBearerToken })
    return { controller: createListingAgentController(client, () => auth.current(), setView) }
  }, [apiBaseUrl, apiKey, getBearerToken])
  useEffect(() => { controller.activate(); controller.load(); return () => controller.dispose() }, [controller])
  useEffect(() => {
    if (view.session?.stage !== 'analyzing') return undefined
    const timer = setInterval(() => controller.refresh(), 4000)
    return () => clearInterval(timer)
  }, [controller, view.session?.stage])
  const session = view.session
  const pending = session?.pending
  return <section className="panel listing-assistant is-open" aria-label="Listing draft agent">
    <h3>Jouft Listing Agent</h3><p>Create a private draft. Nothing is published from this chat.</p>
    {!session && !view.busy && <button onClick={() => controller.retry()}>Connect</button>}
    {session && <>
      <p>{session.photos.length}/6 photos saved · {session.stage.replaceAll('_', ' ')}</p>
      {!session.listing_id && <div>
        <label>Choose the complete photo set (JPEG, PNG or WebP, up to 6)
          <input type="file" accept="image/jpeg,image/png,image/webp" multiple disabled={view.busy} onChange={event => setFiles(Array.from(event.target.files || []).slice(0, 6))} />
        </label>
        <button disabled={view.busy || !files.length} onClick={() => controller.upload(files)}>Use these photos</button>
      </div>}
      <div className="listing-assistant-messages" aria-live="polite">
        {session.messages.map((message, index) => <div key={index} className={`listing-assistant-message ${message.role}`}><p>{message.content}</p></div>)}
      </div>
      {pending?.type === 'confirm_analysis' && <div className="panel">
        <h4>Confirm your draft details</h4>
        <dl>{Object.entries(pending.facts).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>
        {!!pending.waived_views.length && <p>Unavailable views: {pending.waived_views.join(', ')}</p>}
        <button className="primary" disabled={view.busy} onClick={() => controller.confirm()}>Confirm and analyze private draft</button>
      </div>}
      {session.stage === 'analyzing' && <p role="status">Analysis is in progress. You can close this chat and resume later.</p>}
      {session.listing_id && !session.job_id && <button disabled={view.busy} onClick={() => controller.send('Continue the confirmed private draft and start its analysis.')}>Continue saved draft</button>}
      {session.listing && <div className="panel"><h4>{session.listing.title}</h4>
        <p>{session.listing.brand} · {session.listing.condition} · {session.listing.size}</p>
        <p>{session.listing.description}</p>
        {session.stage === 'review_ready' && <p>{session.listing.estimated_value > 0 ? `Estimated value: $${session.listing.estimated_value}` : 'Value needs review.'} Review and edit this private draft in My Closet.</p>}
        {session.stage === 'failed' && <p>Analysis did not finish. The draft is saved in My Closet.</p>}
        {session.stage === 'closed' && <p>This listing changed outside this conversation. Continue in My Closet.</p>}
      </div>}
      {!session.listing_id && <form onSubmit={event => { event.preventDefault(); if (!text.trim()) return; controller.send(text); setText('') }}>
        <label>Your reply<textarea value={text} onChange={event => setText(event.target.value)} maxLength={2000} disabled={view.busy} /></label>
        <button disabled={view.busy || !text.trim()}>Send</button>
      </form>}
      <button disabled={view.busy} onClick={() => { setFiles([]); controller.startNew() }}>Start another draft</button>
    </>}
    {view.busy && <p role="status">Working…</p>}
    {view.error && <div role="alert"><p>{view.error}</p><button disabled={view.busy} onClick={() => controller.retry()}>Retry</button><button disabled={view.busy} onClick={() => controller.refresh()}>Reload saved progress</button></div>}
  </section>
}
