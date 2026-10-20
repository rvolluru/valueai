import { useEffect, useMemo, useRef, useState } from 'react'
import { createWebApiClient } from '../lib/apiClient'
import { createListingAgentController } from '../../../../packages/app-client/src/listingAgent'
import { MANNEQUIN_DISCLAIMER } from '../../../../packages/app-client/src/mannequinDisclosure'

export default function ListingAgentChat({ apiBaseUrl, apiKey, getBearerToken, clerkEnabled, initialListingId = null, onExit = null, onStartNew = null }) {
  const [view, setView] = useState({ session: null, busy: false, error: '' })
  const [text, setText] = useState('')
  const [files, setFiles] = useState([])
  const [mannequinChoice, setMannequinChoice] = useState('')
  const fileInput = useRef(null)
  const auth = useRef(null)
  auth.current = async () => clerkEnabled ? { bearerToken: await getBearerToken() } : { apiKey }
  const { controller } = useMemo(() => {
    const { client } = createWebApiClient({ apiBaseUrl, apiKey, getBearerToken })
    return { controller: createListingAgentController(client, () => auth.current(), setView) }
  }, [apiBaseUrl, apiKey, getBearerToken, initialListingId])
  useEffect(() => { controller.activate(); controller.load(initialListingId); return () => controller.dispose() }, [controller, initialListingId])
  useEffect(() => {
    if (view.session?.stage !== 'analyzing') return undefined
    const timer = setInterval(() => controller.refresh(), 4000)
    return () => clearInterval(timer)
  }, [controller, view.session?.stage])
  const session = view.session
  const pending = session?.pending
  const proposal = session?.edit_proposal || (pending?.type === 'confirm_changes' ? pending : null)
  const review = session?.publication_review
  const canEdit = !session?.listing_id || session?.stage === 'review_ready'
  const reviewing = !!session?.listing_id
  const displayPhotos = session?.listing && !canEdit ? (session.listing.images || []).map((url, index) => ({ image_id: `review-${index}`, url })) : session?.photos || []
  useEffect(() => { setMannequinChoice('') }, [review?.token])
  return <section className="panel listing-assistant listing-agent-chat is-open" aria-label="Listing draft agent">
    {!reviewing && <p>Add photos to create a private draft. Nothing is published without your confirmation.</p>}
    {onExit && <button className="ghost small" disabled={view.busy} onClick={onExit}>Back to conversation</button>}
    {!session && !view.busy && <button onClick={() => controller.retry()}>Connect</button>}
    {session && <>
      {!reviewing && <p>{session.photos.length}/6 photos saved</p>}
      {session.photo_dirty && <p role="status">Photo changes are staged only. Confirm the proposed changes before they are applied to the listing.</p>}
      <details className="listing-agent-photo-details" open={!reviewing || undefined}>
      <summary>Photos ({session.photos.length}) · View or change</summary>
      <div className="listing-agent-photos" aria-label="Saved photos">
        {displayPhotos.map((photo, index) => <figure key={photo.image_id}>
          <img src={new URL(photo.url, apiBaseUrl || window.location.origin).href} alt={`Saved item photo ${index + 1}`} />
          {review?.mannequin_assets.some(asset => asset.image_url === photo.url) && <figcaption>{MANNEQUIN_DISCLAIMER}</figcaption>}
          {canEdit && <button type="button" disabled={view.busy} aria-label={`Remove photo ${index + 1}`} onClick={() => controller.removePhoto(photo.image_id)}>Remove</button>}
        </figure>)}
      </div>
      {canEdit && <div>
        <label>Add photos (JPEG, PNG or WebP, up to 6 saved in total)
          <input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" multiple disabled={view.busy || session.photos.length >= 6} onChange={event => setFiles(Array.from(event.target.files || []))} />
        </label>
        {!!files.length && <p role="status">{files.length} photos selected, not uploaded yet. Press “Use these photos” before replying. Existing photos stay saved.</p>}
        {session.photos.length >= 6 && <p>All 6 photo slots are filled. Remove a photo to add another.</p>}
        <button disabled={view.busy || !files.length} onClick={() => controller.upload(files, () => { setFiles([]); if (fileInput.current) fileInput.current.value = '' })}>Use these photos</button>
        {!!files.length && <button type="button" disabled={view.busy} onClick={() => { setFiles([]); if (fileInput.current) fileInput.current.value = '' }}>Clear selected photos</button>}
      </div>}
      </details>
      <details className="listing-agent-history" open={!reviewing || undefined}>
      <summary>Conversation history</summary>
      <div className="listing-assistant-messages">
        {session.messages.map((message, index) => <div key={index} className={`listing-assistant-message ${message.role}`}><p>{message.content}</p></div>)}
      </div>
      </details>
      {reviewing && !proposal && session.stage === 'review_ready' && <p role="status">{session.messages.filter(message => message.role === 'assistant').at(-1)?.content}</p>}
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
        <details><summary>Item description</summary><p>{session.listing.description}</p></details>
        {session.stage === 'review_ready' && <>
          <p>{session.listing.estimated_value > 0 ? `Estimated value: $${session.listing.estimated_value}` : 'Value needs review.'}</p>
          {!proposal && <p>To make a correction, tell me below—for example, “Change size to US 10.5.”</p>}
          <button disabled={view.busy} onClick={() => controller.send('Keep as draft')}>Keep as draft</button>
          {review?.mannequin_choice_required && <fieldset disabled={view.busy}><legend>Include the AI-generated mannequin image?</legend>
            {review.mannequin_assets.map((asset, index) => asset.image_url && <figure key={index}><img src={new URL(asset.image_url, apiBaseUrl || window.location.origin).href} alt="AI-generated mannequin preview" style={{ width: '100%', maxHeight: 280, objectFit: 'contain' }} /><figcaption>{MANNEQUIN_DISCLAIMER}</figcaption></figure>)}
            {['include', 'exclude'].map(choice => <label key={choice}><input type="radio" name={`mannequin-${session.session_id}`} value={choice} checked={mannequinChoice === choice} onChange={() => setMannequinChoice(choice)} />{choice === 'include' ? 'Include mannequin image' : 'Use original photos only'}</label>)}
          </fieldset>}
          {proposal && <div className="panel" aria-label="Proposed listing changes">
            <h4>Save these changes?</h4>
            {Object.entries(proposal.changes || {}).map(([key, value]) => <p key={key}>{key}: {session.listing[key] || 'Not set'} → {value}</p>)}
            <p>{session.photos.length} photos. {proposal.reanalyze ? 'This will run analysis again before publication.' : 'The existing analysis and value will be retained.'}</p>
            <p>Reply “Save changes” to apply these staged changes, or “Discard changes” to cancel.</p>
          </div>}
          {!proposal && review?.reasons.map(reason => <p key={reason} role="status">{reason}</p>)}
          {!proposal && review?.publishable && <button className="primary" disabled={view.busy || !!files.length || !review.publishable || (review.mannequin_choice_required && !mannequinChoice)} onClick={() => controller.publish(mannequinChoice || null)}>Confirm and publish to Marketplace</button>}
        </>}
        {session.stage === 'published' && <p role="status">Published to Marketplace.</p>}
        {session.stage === 'failed' && <p>Analysis did not finish. The draft is saved in My Closet.</p>}
        {session.stage === 'closed' && <div><p>This listing changed. Reopen review to see the current saved version.</p>
          {session.photo_dirty && <button disabled={view.busy} onClick={() => controller.send('Discard changes')}>Discard staged changes</button>}
          <button disabled={view.busy} onClick={() => controller.load(session.listing_id)}>Reopen review</button></div>}
      </div>}
      {canEdit && <form onSubmit={event => { event.preventDefault(); if (!text.trim() || files.length) return; controller.send(text); setText('') }}>
        <label>{reviewing ? 'Ask a question or describe a correction' : 'Your reply'}<textarea value={text} onChange={event => setText(event.target.value)} maxLength={2000} disabled={view.busy} /></label>
        <button disabled={view.busy || !text.trim() || !!files.length}>Send</button>
      </form>}
      <button disabled={view.busy} onClick={async () => { setFiles([]); if (fileInput.current) fileInput.current.value = ''; if (await controller.startNew()) onStartNew?.() }}>Start another draft</button>
    </>}
    {view.busy && <p role="status">Working…</p>}
    {view.error && <div role="alert"><p>{view.error}</p><button disabled={view.busy} onClick={() => controller.retry()}>Retry</button><button disabled={view.busy} onClick={() => controller.refresh()}>Reload saved progress</button></div>}
  </section>
}
