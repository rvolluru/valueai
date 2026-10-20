import { useEffect, useMemo, useRef, useState } from 'react'
import { createWebApiClient } from '../lib/apiClient'
import { createListingAgentController } from '../../../../packages/app-client/src/listingAgent'
import { MANNEQUIN_DISCLAIMER } from '../../../../packages/app-client/src/mannequinDisclosure'

export default function ListingAgentChat({ apiBaseUrl, apiKey, getBearerToken, clerkEnabled, initialListingId = null, onExit = null, onStartNew = null }) {
  const [view, setView] = useState({ session: null, busy: false, error: '' })
  const [text, setText] = useState('')
  const [files, setFiles] = useState([])
  const [mannequinChoice, setMannequinChoice] = useState('')
  const [editFields, setEditFields] = useState(null)
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
  const review = session?.publication_review
  const canEdit = !session?.listing_id || session?.stage === 'review_ready'
  const displayPhotos = session?.listing && !canEdit ? (session.listing.images || []).map((url, index) => ({ image_id: `review-${index}`, url })) : session?.photos || []
  useEffect(() => { setMannequinChoice('') }, [review?.token])
  return <section className="panel listing-assistant listing-agent-chat is-open" aria-label="Listing draft agent">
    <h3>Jouft Listing Agent</h3><p>Create a private draft, review the results, and publish only after your confirmation.</p>
    {onExit && <button disabled={view.busy} onClick={onExit}>Back to assistant</button>}
    {!session && !view.busy && <button onClick={() => controller.retry()}>Connect</button>}
    {session && <>
      <p>{session.photos.length}/6 photos saved · {session.stage.replaceAll('_', ' ')}</p>
      {session.photo_dirty && <p role="status">Photo changes are staged only. Confirm the proposed changes before they are applied to the listing.</p>}
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
      {pending?.type === 'confirm_changes' && <div className="panel">
        <h4>Confirm proposed changes</h4>
        {Object.entries(pending.changes).map(([key, value]) => <p key={key}>{key}: {value}</p>)}
        <p>{pending.photo_count} photos. {pending.reanalyze ? 'This will run analysis again before publication.' : 'The existing analysis and value will be retained.'}</p>
        <button disabled={view.busy} onClick={() => controller.confirmEdits()}>Confirm changes</button>
        <button disabled={view.busy} onClick={() => controller.send('Discard changes')}>Discard changes</button>
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
        {session.stage === 'review_ready' && <>
          <p>{session.listing.estimated_value > 0 ? `Estimated value: $${session.listing.estimated_value}` : 'Value needs review.'}</p>
          <p>Review the details and photos. Describe a correction below or use Edit details before publishing.</p>
          <button disabled={view.busy} onClick={() => setEditFields(Object.fromEntries(['title', 'brand', 'category', 'condition', 'size', 'description'].map(key => [key, session.listing[key] || ''])))}>Edit details</button>
          <button disabled={view.busy} onClick={() => controller.send('Keep as draft')}>Keep as draft</button>
          {editFields && <form onSubmit={async event => { event.preventDefault(); if (await controller.proposeEdits(editFields)) setEditFields(null) }}>
            {['title', 'brand', 'description'].map(key => <label key={key}>{key}<textarea value={editFields[key]} maxLength={key === 'description' ? 4000 : key === 'title' ? 300 : 200} onChange={event => setEditFields({ ...editFields, [key]: event.target.value })} /></label>)}
            {['category', 'condition', 'size'].map(key => <label key={key}>{key}<select required value={editFields[key]} onChange={event => setEditFields({ ...editFields, [key]: event.target.value, ...(key === 'category' ? { size: '' } : {}) })}>
              <option value="">Select {key}</option>
              {(key === 'category' ? ['clothes', 'shoes', 'handbag', 'accessories'] : key === 'condition' ? ['NewWithTags', 'New', 'LikeNew'] : (session.size_options_by_category?.[editFields.category] || session.size_options)).map(value => <option key={value} value={value}>{value}</option>)}
            </select></label>)}
            <button disabled={view.busy}>Review proposed changes</button><button type="button" onClick={() => setEditFields(null)}>Cancel editing</button>
          </form>}
          {review?.mannequin_choice_required && <fieldset disabled={view.busy}><legend>Include the AI-generated mannequin image?</legend>
            {review.mannequin_assets.map((asset, index) => asset.image_url && <figure key={index}><img src={new URL(asset.image_url, apiBaseUrl || window.location.origin).href} alt="AI-generated mannequin preview" style={{ width: '100%', maxHeight: 280, objectFit: 'contain' }} /><figcaption>{MANNEQUIN_DISCLAIMER}</figcaption></figure>)}
            {['include', 'exclude'].map(choice => <label key={choice}><input type="radio" name={`mannequin-${session.session_id}`} value={choice} checked={mannequinChoice === choice} onChange={() => setMannequinChoice(choice)} />{choice === 'include' ? 'Include mannequin image' : 'Use original photos only'}</label>)}
          </fieldset>}
          {review?.reasons.map(reason => <p key={reason} role="status">{reason}</p>)}
          {review && <button className="primary" disabled={view.busy || !!editFields || !!files.length || !review.publishable || (review.mannequin_choice_required && !mannequinChoice)} onClick={() => controller.publish(mannequinChoice || null)}>Confirm and publish to Marketplace</button>}
          <button disabled={view.busy} onClick={() => controller.refresh()}>Reload saved progress</button>
        </>}
        {session.stage === 'published' && <p role="status">Published to Marketplace.</p>}
        {session.stage === 'failed' && <p>Analysis did not finish. The draft is saved in My Closet.</p>}
        {session.stage === 'closed' && <div><p>This listing changed. Reopen review to see the current saved version.</p>
          {session.photo_dirty && <button disabled={view.busy} onClick={() => controller.send('Discard changes')}>Discard staged changes</button>}
          <button disabled={view.busy} onClick={() => controller.load(session.listing_id)}>Reopen review</button></div>}
      </div>}
      {canEdit && <form onSubmit={event => { event.preventDefault(); if (!text.trim() || files.length) return; controller.send(text); setText('') }}>
        <label>Your reply<textarea value={text} onChange={event => setText(event.target.value)} maxLength={2000} disabled={view.busy} /></label>
        <button disabled={view.busy || !text.trim() || !!files.length}>Send</button>
      </form>}
      <button disabled={view.busy} onClick={async () => { setFiles([]); if (fileInput.current) fileInput.current.value = ''; if (await controller.startNew()) onStartNew?.() }}>Start another draft</button>
    </>}
    {view.busy && <p role="status">Working…</p>}
    {view.error && <div role="alert"><p>{view.error}</p><button disabled={view.busy} onClick={() => controller.retry()}>Retry</button><button disabled={view.busy} onClick={() => controller.refresh()}>Reload saved progress</button></div>}
  </section>
}
