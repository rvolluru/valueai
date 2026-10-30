import { useEffect, useMemo, useRef, useState } from 'react'
import { createWebApiClient } from '../lib/apiClient'
import { createListingAgentController, photoCoverageSummary } from '../../../../packages/app-client/src/listingAgent'
import { MANNEQUIN_DISCLAIMER } from '../../../../packages/app-client/src/mannequinDisclosure'
import { matchPhotoUrls } from '../../../../packages/app-client/src/matchPhotos'

export default function ListingAgentChat({ apiBaseUrl, apiKey, getBearerToken, clerkEnabled, initialListingId = null, initialSessionId = null, newSessionRequestId = null, onExit = null, onStartNew = null, onOpenPhotos = null, onContext = null, onBusyChange = null, hideComposer = false, onTranscript = null, onPhotoPanel = null }) {
  const [view, setView] = useState({ session: null, busy: false, error: '' })
  const [text, setText] = useState('')
  const transcriptCallback = useRef(onTranscript)
  transcriptCallback.current = onTranscript
  useEffect(() => { if (view.session) {
    const question = view.session.pending?.type === 'question' ? view.session.pending : !view.session.pending ? view.session.next_step : null
    transcriptCallback.current?.({ session_id: view.session.session_id, stage: view.session.stage, messages: view.session.messages, timeline_events: view.session.timeline_events, conditionQuestion: question?.question, conditionRequested: question?.field === 'condition' })
  } }, [view.session])
  const [files, setFiles] = useState([])
  const busyCallback = useRef(onBusyChange)
  busyCallback.current = onBusyChange
  useEffect(() => { busyCallback.current?.(view.busy); return () => busyCallback.current?.(false) }, [view.busy])
  const [mannequinChoice, setMannequinChoice] = useState('')
  const fileInput = useRef(null)
  const contextCallback = useRef(onContext)
  const photoCallback = useRef(onOpenPhotos)
  const openedPhotoRequest = useRef(null)
  contextCallback.current = onContext
  photoCallback.current = onOpenPhotos
  useEffect(() => { if (view.session?.conversation_context) contextCallback.current?.(view.session.conversation_context) }, [view.session?.conversation_context])
  useEffect(() => {
    const photo = view.session?.photo_view
    if (!photo?.images?.length || openedPhotoRequest.current === photo.request_id) return
    openedPhotoRequest.current = photo.request_id
    photoCallback.current?.({ images: matchPhotoUrls(photo, apiBaseUrl || window.location.origin), title: photo.title, listing: photo })
  }, [view.session?.photo_view, apiBaseUrl])
  const auth = useRef(null)
  auth.current = async () => clerkEnabled ? { bearerToken: await getBearerToken() } : { apiKey }
  const { controller } = useMemo(() => {
    const { client } = createWebApiClient({ apiBaseUrl, apiKey, getBearerToken })
    return { controller: createListingAgentController(client, () => auth.current(), setView) }
  }, [apiBaseUrl, apiKey, getBearerToken, initialListingId, newSessionRequestId, initialSessionId])
  useEffect(() => { controller.activate(); controller.load(initialListingId, newSessionRequestId, initialSessionId); return () => controller.dispose() }, [controller, initialListingId, newSessionRequestId, initialSessionId])
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
  const photoPanel = session && <>
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
      {!onPhotoPanel && !!photoCoverageSummary(session).length && <section aria-label="Photo coverage" className="listing-photo-coverage" role="status">
        <h4>Photo coverage</h4>
        {photoCoverageSummary(session).map((line, index) => <p key={index}>{line}</p>)}
      </section>}
  </>
  const panelCallback = useRef(onPhotoPanel)
  panelCallback.current = onPhotoPanel
  useEffect(() => { if (session) panelCallback.current?.({ session_id: session.session_id, node: photoPanel }) }, [session, view.busy, files])
  return <section className="panel listing-assistant listing-agent-chat is-open" aria-label="Listing draft agent">
    {!hideComposer && !reviewing && <p>Add photos to create a private draft. Nothing is published without your confirmation.</p>}
    {onExit && <button className="ghost small" disabled={view.busy} onClick={onExit}>{hideComposer ? 'Hide listing photos and review' : 'Back to conversation'}</button>}
    {!session && !view.busy && <button onClick={() => controller.retry()}>Connect</button>}
    {session && <>
      {!onPhotoPanel && photoPanel}
      {!hideComposer && <details className="listing-agent-history" open={!reviewing || undefined}>
      <summary>Conversation history</summary>
      <div className="listing-assistant-messages">
        {session.messages.map((message, index) => <div key={index} className={`listing-assistant-message ${message.role}`}><p>{message.content}</p></div>)}
      </div>
      </details>}
      {!hideComposer && reviewing && !proposal && session.stage === 'review_ready' && <p role="status">{session.messages.filter(message => message.role === 'assistant').at(-1)?.content}</p>}
      {pending?.type === 'confirm_analysis' && <div className="panel">
        <h4>Confirm your draft details</h4>
        <dl className="listing-confirm-facts">{Object.entries(pending.facts).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl>
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
          {!proposal && <p>To make a correction, tell me what you would like to change below.</p>}
          <button className="ghost small" disabled={view.busy} onClick={() => controller.send('Keep as draft')}>Keep as draft</button>
          {review?.mannequin_choice_required && <fieldset className="listing-mannequin-choice" disabled={view.busy}><legend>Choose your listing photos</legend>
            <p className="listing-control-hint">Include the AI styling preview, or use only your original photos.</p>
            <div className="listing-mannequin-layout">
            <div className="listing-mannequin-previews">{review.mannequin_assets.map((asset, index) => asset.image_url && <figure key={index}><img src={new URL(asset.image_url, apiBaseUrl || window.location.origin).href} alt="AI-generated mannequin preview" /><figcaption>{MANNEQUIN_DISCLAIMER}</figcaption></figure>)}</div>
            <div className="listing-mannequin-options">{['include', 'exclude'].map(choice => <label className={`listing-choice-card${mannequinChoice === choice ? ' is-selected' : ''}`} key={choice}>
              <input type="radio" name={`mannequin-${session.session_id}`} value={choice} checked={mannequinChoice === choice} onChange={() => setMannequinChoice(choice)} />
              <span><strong>{choice === 'include' ? 'Include mannequin image' : 'Use original photos only'}</strong><small>{choice === 'include' ? 'Add the AI styling preview alongside your photos.' : 'Show only the photos you uploaded.'}</small></span>
            </label>)}</div>
            </div>
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
        {session.stage === 'published' && <><p role="status">Published to Marketplace.</p>
          <button className="primary" disabled={view.busy} onClick={() => controller.send('Find marketplace matches')}>{session.marketplace_matches ? 'Refresh matches' : 'Find matching items'}</button>
        </>}
        {session.stage === 'failed' && <p>Analysis did not finish. The draft is saved in My Closet.</p>}
        {session.stage === 'closed' && <div><p>This listing changed. Reopen review to see the current saved version.</p>
          {session.photo_dirty && <button disabled={view.busy} onClick={() => controller.send('Discard changes')}>Discard staged changes</button>}
          <button disabled={view.busy} onClick={() => controller.load(session.listing_id)}>Reopen review</button></div>}
      </div>}
      {session.stage === 'published' && session.marketplace_matches && !session.trade_proposal && <section aria-label="Marketplace matches">
        <h4>Marketplace matches</h4>
        <p>Selecting an item only prepares a request; confirmation is required to send.</p>
        {session.marketplace_matches.items.map(item => <article className="panel listing-agent-match-card" key={item.listing_id}>
          {matchPhotoUrls(item, apiBaseUrl || window.location.origin).length > 0 && <button type="button" className="listing-agent-match-photo" aria-label={`View full-size photos of ${item.title}`} disabled={view.busy} onClick={() => controller.viewPhotos(item.listing_id)}>
            <img src={matchPhotoUrls(item, apiBaseUrl || window.location.origin)[0]} alt={item.title} loading="lazy" />
          </button>}
          <div className="listing-agent-match-details">
            <p className="listing-agent-match-brand">{item.brand}</p>
            <h4>{item.title}</h4>
            <div className="listing-agent-match-meta">
              {item.size && <span>Size {item.size}</span>}
              {item.condition && <span>{({ LikeNew: 'Like new', NewWithTags: 'New with tags' })[item.condition] || item.condition}</span>}
              <span className="listing-agent-match-value">${item.estimated_value}</span>
            </div>
            <div className="listing-agent-match-actions">
              <a href={`/?tab=market&listing=${encodeURIComponent(item.listing_id)}`}>View in Marketplace</a>
              <button className="primary" disabled={view.busy} onClick={() => controller.prepareTrade(item.listing_id)}>Request trade</button>
            </div>
          </div>
        </article>)}
        {!session.marketplace_matches.count && <p>No matching items right now. Check again later.</p>}
        {session.marketplace_matches.has_more && <p>Showing the first {session.marketplace_matches.items.length} of {session.marketplace_matches.count} matches.</p>}
      </section>}
      {session.trade_proposal && <section className="panel" aria-label="Confirm trade request">
        <h4>Send this trade request?</h4>
        <p>You offer: {session.trade_proposal.offered.title} · {session.trade_proposal.offered.size} · {session.trade_proposal.offered.condition} · ${session.trade_proposal.offered.estimated_value}</p>
        <p>You request: {session.trade_proposal.target.title} · {session.trade_proposal.target.size} · {session.trade_proposal.target.condition} · ${session.trade_proposal.target.estimated_value}</p>
        <p>This offers your item to {session.trade_proposal.recipient} and notifies them. It does not complete the trade or charge a payment.</p>
        <button className="primary" disabled={view.busy} onClick={() => controller.confirmTrade()}>Confirm and send trade request</button>
        <button className="ghost" disabled={view.busy} onClick={() => controller.send('Cancel trade request')}>Cancel trade request</button>
      </section>}
      {session.sent_trade && <p role="status">Trade request sent. Track it in <a href="/?tab=inbox">Trade Inbox</a>.</p>}
      {session.existing_trade && <p role="status">Existing trade request · {session.existing_trade.status}. {session.existing_trade.same_items ? 'Same two items.' : 'Different offered items.'} <a href="/?tab=inbox">View Trade Inbox</a>.</p>}
      {!hideComposer && canEdit && pending?.type === 'question' && pending.field === 'condition' && <div role="group" aria-label="Choose item condition" className="listing-chat-quick-replies">
        {['New with tags', 'New', 'Like new'].map(condition => <button key={condition} type="button" className="ghost small" disabled={view.busy || !!files.length} onClick={() => controller.send(condition)}>{condition}</button>)}
      </div>}
      {!hideComposer && (canEdit || session.stage === 'published') && <form onSubmit={event => { event.preventDefault(); if (!text.trim() || files.length) return; controller.send(text); setText('') }}>
        <label>{reviewing ? 'Ask a question or describe a correction' : 'Your reply'}<textarea value={text} onChange={event => setText(event.target.value)} maxLength={2000} disabled={view.busy} /></label>
        <button disabled={view.busy || !text.trim() || !!files.length}>Send</button>
      </form>}
      {!initialSessionId && <button disabled={view.busy} onClick={async () => { setFiles([]); if (fileInput.current) fileInput.current.value = ''; if (await controller.startNew()) onStartNew?.() }}>Start another draft</button>}
    </>}
    {view.busy && <p role="status">Working…</p>}
    {view.error && <div role="alert"><p>{view.error}</p><button disabled={view.busy} onClick={() => controller.retry()}>Retry</button><button disabled={view.busy} onClick={() => controller.refresh()}>Reload saved progress</button></div>}
  </section>
}
