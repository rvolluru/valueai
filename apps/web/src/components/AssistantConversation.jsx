import { Fragment, useEffect, useRef, useState } from 'react';
import { createConversationController, conversationBlocks, conversationSpans, assistantOutcomeLabel, resultSetHeading, chronologicalChat, listingPanelPosition, conversationText } from '../../../../packages/app-client/src/assistantConversation';

export default function AssistantConversation({ client, getAuth, onPhotos, renderWorkflow = null }) {
  const [view, setView] = useState({ busy: true });
  const [input, setInput] = useState('');
  const [workflowOpen, setWorkflowOpen] = useState(false);
  const [workflowBusy, setWorkflowBusy] = useState(false);
  const [listingTranscript, setListingTranscript] = useState(null);
  const [photoPanel, setPhotoPanel] = useState(null);
  const linkedTranscript = listingTranscript?.session_id === view.session?.workflow_id ? listingTranscript : null;
  const messages = chronologicalChat(view.session?.messages, linkedTranscript, view.session?.result_sets);
  const hasPhotoEvents = messages.some(m => m.timeline_kind === 'photos');
  const hasActionEvents = messages.some(m => m.timeline_kind === 'actions');
  useEffect(() => { setWorkflowOpen(!!view.session?.workflow_id); }, [view.session?.conversation_id, view.session?.workflow_id]);
  const refs = useRef({ getAuth });
  refs.current = { getAuth };
  const controller = useRef(null);
  const end = useRef(null);
  const openedGallery = useRef(null);
  const photos = useRef(onPhotos);
  photos.current = onPhotos;
  useEffect(() => {
    const event = view.session?.gallery;
    if (event && event.request_id !== openedGallery.current) {
      openedGallery.current = event.request_id;
      photos.current(event.listing);
    }
  }, [view.session]);
  useEffect(() => {
    const current = createConversationController(client, () => refs.current.getAuth(), setView);
    controller.current = current;
    current.start();
    return () => current.dispose();
  }, [client]);
  useEffect(() => { end.current?.scrollIntoView({ block: 'nearest' }); }, [view.session, view.busy, linkedTranscript]);
  const panelIndex = listingPanelPosition(messages, linkedTranscript?.stage);
  const questionIndex = linkedTranscript?.conditionRequested ? messages.findLastIndex(m => m.role === 'assistant' && linkedTranscript.conditionQuestion && conversationText(m).endsWith(linkedTranscript.conditionQuestion)) : -1;
  const conditionButtons = <div className="listing-chat-quick-replies" role="group" aria-label="Choose item condition">{['New with tags', 'New', 'Like new'].map(condition => <button type="button" key={condition} disabled={view.busy || workflowBusy || view.retryable} onClick={() => controller.current.send(condition)}>{condition}</button>)}</div>;
  const listingPanel = view.session?.workflow_id && renderWorkflow && (workflowOpen
    ? <fieldset key={view.session.revision} disabled={view.busy || view.retryable} style={{ border: 0, padding: 0, minWidth: 0 }}>{renderWorkflow(view.session.workflow_id, () => setWorkflowOpen(false), setWorkflowBusy, setListingTranscript, setPhotoPanel)}</fieldset>
    : <button className="primary small" disabled={view.busy} onClick={() => setWorkflowOpen(true)}>Show listing photos and review</button>);
  const inlinePhotos = workflowOpen && photoPanel?.session_id === view.session?.workflow_id && <fieldset className="listing-agent-chat" disabled={view.busy || workflowBusy || view.retryable} style={{ border: 0, padding: 0, minWidth: 0 }}>{photoPanel.node}</fieldset>;
  const renderResults = groups => (groups || []).map(group => <section key={group.id}><h4>{resultSetHeading(group)}</h4>
    <div className="app-assistant-results">{group.items.map((item, index) => <article className={item.image ? 'has-image' : 'is-text-only'} key={item.listing_id || `${item.offer_id}-${index}`}>
      {item.image && <button disabled={view.busy || view.retryable} className="app-assistant-photo-button" type="button" aria-label={`View photos of ${item.title}`} onClick={() => controller.current.viewPhotos(item)}><img src={item.image} alt={item.title} /></button>}
      <div><small>{(group.offset || 0) + index + 1}{item.brand ? ` · ${item.brand}` : ''}</small><strong>{item.title}</strong>{group.domain === 'trades' || group.domain === 'shipping' ? <span>{item.carrier ? `${item.carrier} · ` : ''}{item.status}{item.eta ? ` · Estimated arrival: ${item.eta}` : ''}</span> : <span>{item.size} · {item.condition}</span>}</div>
    </article>)}</div></section>);
  return <div className="assistant-workspace">
    <aside className="assistant-threads" aria-label="Chat threads">
      <h2>Jouft chats</h2>
      <button className="primary small" disabled={view.busy || workflowBusy || view.retryable} onClick={() => { setInput(''); controller.current.newThread(); }}>＋ New chat</button>
      <nav aria-label="Previous chats">{(view.threads || []).map(thread => <button type="button" key={thread.conversation_id} aria-current={view.session?.conversation_id === thread.conversation_id ? 'page' : undefined} disabled={view.busy || workflowBusy || view.retryable} onClick={() => { setInput(''); controller.current.openThread(thread.conversation_id); }}>{thread.title}</button>)}</nav>
    </aside>
    <main className="assistant-conversation-main" aria-label="Conversation">
    <div className="app-assistant-transcript" aria-live="polite">
      <p>Ask me to create a listing, update an existing one, or find Marketplace matches.</p>
      {messages.map((message, index) => <Fragment key={message.id || `${message.request_id || 'legacy'}-${index}`}>
        {!hasPhotoEvents && index === panelIndex && inlinePhotos}
        {message.timeline_kind === 'photos' && message.isCurrent ? inlinePhotos : message.timeline_kind === 'actions' && message.isCurrent ? listingPanel : <div className={`app-assistant-turn ${message.role}`}><div className="assistant-message-body">
          {conversationBlocks(message).map((block, n) => <p key={n} className={`assistant-message-${block.kind}`}>{block.kind === 'bullet' ? '• ' : ''}{conversationSpans(block.text).map((span, i) => span.bold ? <strong key={i}>{span.text}</strong> : <span key={i}>{span.text}</span>)}</p>)}
          {message.timeline_kind === 'photos' && <div className="listing-agent-photos">{(message.snapshot.photos || []).map(photo => <img key={photo.image_id} src={photo.url} alt="Previously uploaded item photo" style={{ maxWidth: 140, maxHeight: 160, objectFit: 'contain' }} />)}</div>}
          {index === questionIndex && conditionButtons}
        </div></div>}
        {renderResults(message.result_sets)}
      </Fragment>)}
      {!hasPhotoEvents && panelIndex === messages.length && inlinePhotos}
      {!hasActionEvents && listingPanel}
      {view.busy && <p role="status">Thinking…</p>}
      {!!view.session?.outcome?.next_actions?.length && <div className="listing-chat-quick-replies" role="group" aria-label="Available next actions">{view.session.outcome.next_actions.map((choice, index) => <button type="button" className="ghost small" key={index} disabled={view.busy || view.retryable} onClick={() => controller.current.nextAction(index)}>{choice.label}</button>)}</div>}
      {assistantOutcomeLabel(view.error ? view.errorCategory : view.session?.outcome?.category) && <p role="status"><strong>{assistantOutcomeLabel(view.error ? view.errorCategory : view.session?.outcome?.category)}</strong></p>}
      {view.error && <p role="alert">{view.error}</p>}
      {view.retryable && <button disabled={view.busy} onClick={() => controller.current.retry()}>Retry saved request</button>}
      <div ref={end} />
    </div>
    {<form className="app-assistant-compose" onSubmit={event => { event.preventDefault(); const message = input.trim(); if (message && !workflowBusy) { controller.current.send(message); setInput(''); } }}>
      <textarea aria-label="Message Jouft" rows={2} value={input} onChange={event => setInput(event.target.value)} disabled={view.busy || workflowBusy || view.retryable || !view.session} />
      <button className="primary small" disabled={!input.trim() || view.busy || workflowBusy || view.retryable || !view.session}>Send</button>
    </form>}
    </main>
  </div>;
}
