import { photoCoverageSummary } from './listingAgent.js';

export function createConversationController(client, auth, change) {
  let state = { session: null, busy: false, error: '', retryable: false };
  let retry = null;
  let disposed = false;
  const newId = () => globalThis.crypto?.randomUUID?.() || `thread-${Date.now()}-${Math.random()}`;
  async function refreshThreads() {
    if (client.listAssistantConversations) {
      const result = await client.listAssistantConversations(await auth());
      emit({ threads: result.items || [] });
      return result.items || [];
    }
    return [];
  }
  const emit = patch => { state = { ...state, ...patch }; if (!disposed) change(state); };
  async function perform(operation) {
    if (state.busy || disposed) return;
    retry = operation;
    emit({ busy: true, error: '', errorCategory: null, retryable: false });
    try {
      const session = await operation();
      retry = null;
      emit({ session });
      try { await refreshThreads(); } catch { /* A list refresh must not fail a committed turn. */ }
      return session;
    } catch (error) {
      const status = error.status || error.statusCode;
      const conflict = status === 409;
      const failure = !status || status >= 500 || status === 429;
      const blocked = [401, 403, 404, 409].includes(status);
      const category = failure ? 'tool_failure' : blocked ? 'blocked' : 'unclear';
      emit({ error: failure ? 'The service could not complete your request. Retry the same saved request.' :
        conflict ? 'This conversation changed. Saved progress has been reloaded; review it before continuing.' :
        status === 401 || status === 403 ? 'Check your sign-in and account access before continuing.' :
        error.message || 'Review your request before continuing.', errorCategory: category, retryable: failure });
      if (!failure) retry = null;
      if (conflict) {
        retry = null;
        if (state.session) {
          try { emit({ session: await client.getAssistantConversation(state.session.conversation_id, await auth()) }); } catch { /* retain error */ }
        }
      }
    } finally { emit({ busy: false }); }
  }
  return {
    start: () => perform(async () => {
      const threads = await refreshThreads();
      return threads.length ? client.getAssistantConversation(threads[0].conversation_id, await auth())
        : client.startAssistantConversation({ request_id: 'read-pilot-v1' }, await auth());
    }),
    newThread() {
      if (state.busy || retry) return;
      const request_id = newId();
      return perform(async () => client.startAssistantConversation({ request_id }, await auth()));
    },
    openThread(key) {
      if (state.busy || retry) return;
      return perform(async () => client.getAssistantConversation(key, await auth()));
    },
    send(message) {
      if (!state.session || state.busy || retry) return;
      const id = state.session.conversation_id;
      const payload = { request_id: globalThis.crypto?.randomUUID?.() || `chat-${Date.now()}-${Math.random()}`,
        expected_revision: state.session.revision, message };
      return perform(async () => client.messageAssistantConversation(id, payload, await auth()));
    },
    retry: () => retry ? perform(retry) : undefined,
    nextAction(index) {
      if (!state.session || state.busy || retry) return;
      const choice = state.session.outcome?.next_actions?.[index];
      if (!choice) return;
      const payload = { request_id: newId(), expected_revision: state.session.revision,
        message: choice.label, action: choice.action, listing_id: choice.listing_id, terms: choice.terms || [],
        result_set_id: choice.result_set_id, offer_id: choice.offer_id };
      const key = state.session.conversation_id;
      return perform(async () => client.readAssistantConversation(key, payload, await auth()));
    },
    viewPhotos(item) {
      if (!state.session || state.busy || retry) return Promise.resolve(null);
      const payload = { request_id: globalThis.crypto?.randomUUID?.() || `photo-${Date.now()}-${Math.random()}`,
        expected_revision: state.session.revision, message: `View photos of ${item.title}`,
        action: 'photos', listing_id: item.listing_id };
      const key = state.session.conversation_id;
      return perform(async () => client.readAssistantConversation(key, payload, await auth()));
    },
    dispose: () => { disposed = true; },
  };
}

export function conversationText(message) {
  return typeof message.content === 'string' ? message.content : message.content?.message || '';
}

// Read-only transcript projection. Child approvals stay in their own ledger.
export function listingConversationMessages(parent = [], child = []) {
  const same = (a, b) => a.role === b.role && conversationText(a) === conversationText(b);
  // Existing sessions have no timestamps. Weave at shared messages rather than
  // appending a second history (parent-dispatched turns appear in both ledgers).
  const lengths = Array.from({ length: parent.length + 1 }, () => Array(child.length + 1).fill(0));
  for (let i = parent.length - 1; i >= 0; i--) for (let j = child.length - 1; j >= 0; j--)
    lengths[i][j] = same(parent[i], child[j]) ? 1 + lengths[i + 1][j + 1] : Math.max(lengths[i + 1][j], lengths[i][j + 1]);
  const merged = [];
  let i = 0, j = 0;
  while (i < parent.length || j < child.length) {
    if (i < parent.length && j < child.length && same(parent[i], child[j])) {
      const a = parent[i++], b = child[j++];
      merged.push({ ...(a.created_at && b.created_at && b.created_at < a.created_at ? b : a),
        ...(a.result_sets ? { result_sets: a.result_sets } : {}) });
    } else if (j >= child.length || (i < parent.length && lengths[i + 1][j] >= lengths[i][j + 1])) merged.push(parent[i++]);
    else merged.push(child[j++]);
  }
  // Timestamped new events are chronological, with stable order within a turn.
  const ordered = chronologicalOrder(merged);
  return ordered.map(message => conversationText(message) === 'I uploaded these original photos. Please check the evidence and guide me through creating a private listing draft.'
    ? { ...message, content: 'Added photos.' } : message);
}

export function listingPanelPosition(messages) {
  // Fallback for sessions predating saved presentation events, at every stage.
  const upload = messages.findLastIndex(m => m.role === 'user' && conversationText(m) === 'Added photos.');
  if (upload >= 0) return upload + 1;
  return messages.length;
}

function chronologicalOrder(items) {
  const times = items.map(item => Date.parse(item.created_at || ''));
  const known = times.filter(Number.isFinite);
  // For old untimed messages retain their relative order around the nearest
  // real clock anchor; one legacy record must not disable sorting newer events.
  return items.map((item, index) => {
    let time = times[index];
    if (!Number.isFinite(time)) {
      const next = times.findIndex((value, i) => i > index && Number.isFinite(value));
      const previous = times.findLastIndex((value, i) => i < index && Number.isFinite(value));
      time = previous < 0 && known.length ? Math.min(...known) - (items.length - index) / 1000 :
        next >= 0 ? times[next] - (next - index) / 1000 : previous >= 0 ? times[previous] + (index - previous) / 1000 : index;
    }
    return { item, time, index };
  }).sort((a, b) => a.time - b.time || a.index - b.index).map(row => row.item);
}

export function chronologicalChat(parent = [], child = null, currentResults = []) {
  let messages = listingConversationMessages(parent, child?.messages || []);
  const events = child?.timeline_events || [];
  // The upload card is the user event. Do not also display its transport message.
  if (events.some(event => event.kind === 'photos')) messages = messages.filter(m => conversationText(m) !== 'Added photos.');
  if (currentResults.length && !messages.some(m => Object.hasOwn(m, 'result_sets'))) {
    const last = messages.findLastIndex(m => m.role === 'assistant');
    if (last >= 0) messages = messages.map((m, index) => index === last ? { ...m, result_sets: currentResults } : m);
  }
  const latest = Object.fromEntries(events.map(event => [event.kind, event.id]));
  const cards = events.map(event => {
    const snapshot = event.snapshot || {};
    let content = '';
    if (event.kind === 'photos') content = snapshot.photos?.length ? 'Photos added or updated.' : 'Photos removed.';
    if (event.kind === 'coverage') content = 'Photo coverage\n' + (snapshot.evidence ? photoCoverageSummary(snapshot).join('\n') : 'The changed photo set has not been assessed yet.');
    if (event.kind === 'actions') {
      const facts = snapshot.listing?.title ? snapshot.listing : snapshot.facts || {};
      content = (snapshot.pending_type === 'confirm_analysis' ? 'Draft details ready for confirmation.' :
        snapshot.stage === 'review_ready' ? 'Listing review ready.' : `Listing status: ${snapshot.stage}.`) + '\n' +
        ['title', 'brand', 'category', 'condition', 'size', 'estimated_value'].filter(key => facts[key] != null)
          .map(key => key === 'estimated_value'
            ? `Estimated value: ${new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: Number.isInteger(Number(facts[key])) ? 0 : 2, maximumFractionDigits: 2 }).format(Number(facts[key]))}`
            : `${key.replaceAll('_', ' ')}: ${facts[key]}`).join('\n');
      if (snapshot.changes) content += '\nProposed changes: ' + Object.entries(snapshot.changes).map(([key, value]) => `${key}: ${value}`).join(', ');
      if (snapshot.trade?.target) content += `\nTrade: ${snapshot.trade.offered?.title || 'your item'} for ${snapshot.trade.target.title}.`;
      if (snapshot.sent_trade) content += `\nTrade request sent. Status: ${snapshot.sent_trade.status || 'sent'}.`;
    }
    return { ...event, role: event.kind === 'photos' ? 'user' : 'assistant', content,
      timeline_kind: event.kind, isCurrent: latest[event.kind] === event.id,
      ...(event.kind === 'actions' && snapshot.matches && latest[event.kind] !== event.id ? {
        result_sets: [{ id: event.id + '-matches', domain: 'marketplace', count: snapshot.matches.count, items: snapshot.matches.items }],
      } : {}) };
  });
  return chronologicalOrder([...messages, ...cards]);
}

export function assistantOutcomeLabel(category) {
  return { unclear: 'More information needed', unsupported: 'Not supported in this chat',
    blocked: 'Requirement or access issue', tool_failure: 'Temporary service issue' }[category] || '';
}

export function resultSetHeading(group) {
  const title = group.source_listing_id ? `Matches for ${group.source_title || 'your item'}` :
    ({ closet: 'Your closet', marketplace: 'Marketplace', trades: 'Trade inbox', shipping: 'Shipment status' }[group.domain] || 'Results');
  const start = (group.offset || 0) + 1;
  const end = (group.offset || 0) + group.items.length;
  return `${title} · ${group.items.length ? `Showing ${start}–${end} of ${group.count}` : 'No results'}`;
}

// Render text only: never interpret model output as HTML or executable links.
export function conversationBlocks(message) {
  let text = conversationText(message).replace(/\r\n/g, '\n');
  if (message.role !== 'user') {
    // Also clean older saved replies that dumped transport metadata into prose.
    text = text.replace(/(?:^|\s)-?\s*Listing ID:\s*[a-z0-9-]+/gi, '')
      .replace(/(?:^|\s)-?\s*Images?:\s*(?:(?:https?:\/\/\S+|\/v1\/images\/[^\s,]+)[,\s]*)+/gi, '\n\n')
      .replace(/\s+-\s+(?=(?:Title|Brand|Category|Condition|Size|Status|Owner|Estimated value):)/g, '\n- ');
  }
  return text.split('\n').map(line => line.trim()).filter(Boolean).map(line => {
    const bullet = /^(?:[-*•]|\d+[.)])\s+/.test(line);
    const heading = /^#{1,6}\s+/.test(line);
    return { kind: bullet ? 'bullet' : heading ? 'heading' : 'paragraph',
      text: line.replace(/^(?:#{1,6}\s+|[-*•]\s+|\d+[.)]\s+)/, '') };
  });
}

export function conversationSpans(text) {
  return text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map(value => ({
    bold: value.startsWith('**') && value.endsWith('**'),
    text: value.startsWith('**') && value.endsWith('**') ? value.slice(2, -2) : value,
  }));
}
