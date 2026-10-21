import test from 'node:test';
import assert from 'node:assert/strict';
import { createConversationController, conversationText } from './assistantConversation.js';
import { conversationBlocks, conversationSpans } from './assistantConversation.js';
import { resultSetHeading } from './assistantConversation.js';

test('paged results show absolute ranges and status groups have correct headings', () => {
  assert.equal(resultSetHeading({ domain: 'closet', offset: 12, count: 25, items: Array(12) }), 'Your closet · Showing 13–24 of 25');
  assert.equal(resultSetHeading({ domain: 'shipping', count: 0, items: [] }), 'Shipment status · No results');
});

test('more-results action preserves the server result-set reference', async () => {
  let sent;
  const client = {
    startAssistantConversation: async () => ({ conversation_id: 'id', revision: 7,
      outcome: { next_actions: [{ action: 'more', result_set_id: 'saved-query:0', label: 'Show more results' }] } }),
    readAssistantConversation: async (id, payload) => { sent = payload; return { conversation_id: id, revision: 8 }; },
  };
  const controller = createConversationController(client, async () => ({}), () => {});
  await controller.start();
  await controller.nextAction(0);
  assert.equal(sent.result_set_id, 'saved-query:0');
  assert.equal(sent.expected_revision, 7);
  assert.equal(sent.action, 'more');
  assert.equal(sent.offset, undefined);
});

test('access blocks do not offer a blind retry while temporary failures do', async () => {
  let latest;
  const client = {
    startAssistantConversation: async () => ({ conversation_id: 'id', revision: 0 }),
    messageAssistantConversation: async () => { throw Object.assign(Error('Forbidden'), { status: 403 }); },
  };
  const controller = createConversationController(client, async () => ({}), view => { latest = view; });
  await controller.start();
  await controller.send('Read item');
  assert.equal(latest.errorCategory, 'blocked');
  assert.equal(latest.retryable, false);
  client.messageAssistantConversation = async () => { throw Object.assign(Error('Service unavailable'), { status: 503 }); };
  await controller.send('Read closet');
  assert.equal(latest.errorCategory, 'tool_failure');
  assert.equal(latest.retryable, true);
});

test('thread switching loads saved state and new chat uses a fresh creation key', async () => {
  let latest;
  const keys = [];
  const client = {
    listAssistantConversations: async () => ({ items: [{ conversation_id: 'old', title: 'Earlier chat' }] }),
    getAssistantConversation: async id => ({ conversation_id: id, revision: 3, messages: ['saved'] }),
    startAssistantConversation: async payload => { keys.push(payload.request_id); return { conversation_id: payload.request_id, revision: 0, messages: [], focus: null }; },
  };
  const controller = createConversationController(client, async () => ({}), view => { latest = view; });
  await controller.start();
  assert.equal(latest.session.conversation_id, 'old');
  await controller.newThread();
  assert.deepEqual(latest.session.messages, []);
  await controller.newThread();
  assert.notEqual(keys[0], keys[1]);
  await controller.openThread('old');
  assert.deepEqual(latest.session.messages, ['saved']);
});

test('only indexed server-provided next actions are dispatched', async () => {
  const calls = [];
  const client = {
    startAssistantConversation: async () => ({ conversation_id: 'id', revision: 4,
      outcome: { next_actions: [{ action: 'matches', listing_id: 'source', terms: [], label: 'Refresh matches' }] } }),
    readAssistantConversation: async (id, payload) => { calls.push(payload); return { conversation_id: id, revision: 5 }; },
  };
  const controller = createConversationController(client, async () => ({}), () => {});
  await controller.start();
  await controller.nextAction(99);
  assert.equal(calls.length, 0);
  await controller.nextAction(0);
  assert.equal(calls[0].action, 'matches');
  assert.equal(calls[0].listing_id, 'source');
  assert.equal(calls[0].expected_revision, 4);
});

test('replies preserve paragraphs, bullets and bold without rendering HTML', () => {
  const blocks = conversationBlocks({ role: 'assistant', content: '## Details\n\n- **Brand:** Chanel\n- Size: US 10\n\n<script>text only</script>' });
  assert.deepEqual(blocks.map(b => b.kind), ['heading', 'bullet', 'bullet', 'paragraph']);
  assert.deepEqual(conversationSpans(blocks[1].text)[0], { bold: true, text: 'Brand:' });
  assert.equal(blocks[3].text, '<script>text only</script>');
});

test('saved metadata dumps are cleaned and inline field lists become readable', () => {
  const blocks = conversationBlocks({ role: 'assistant', content: 'Details: - Listing ID: 45d2ad41-b7e7-5501-92ed-aaea35b52558 - Title: Coat - Brand: LV - Images: /v1/images/abc, /v1/images/def Would you like photos?' });
  const text = blocks.map(b => b.text).join('\n');
  assert.doesNotMatch(text, /Listing ID|45d2ad41|\/v1\/images/);
  assert.match(text, /Title: Coat\nBrand: LV/);
  assert.match(text, /Would you like photos/);
});

test('parent conversation resumes and retry preserves request ID/revision', async () => {
  let latest;
  const payloads = [];
  const client = {
    startAssistantConversation: async () => ({ conversation_id: 'owner-session', revision: 3 }),
    messageAssistantConversation: async (id, payload) => {
      payloads.push(payload);
      if (payloads.length === 1) throw Error('lost response');
      return { conversation_id: id, revision: 4 };
    },
  };
  const controller = createConversationController(client, async () => ({}), view => { latest = view; });
  await controller.start();
  await controller.send('Find matches for my items');
  assert.equal(latest.retryable, true);
  await controller.send('Do not replace pending request');
  assert.equal(payloads.length, 1);
  await controller.retry();
  assert.deepEqual(payloads[1], payloads[0]);
  assert.equal(latest.session.revision, 4);
  assert.equal(conversationText({ content: { message: 'saved input' } }), 'saved input');
});

test('stale turn reloads without silently resubmitting', async () => {
  let latest;
  let sends = 0;
  const client = {
    startAssistantConversation: async () => ({ conversation_id: 'id', revision: 0 }),
    messageAssistantConversation: async () => { sends++; throw Object.assign(Error('Reload'), { status: 409 }); },
    getAssistantConversation: async () => ({ conversation_id: 'id', revision: 2 }),
  };
  const controller = createConversationController(client, async () => ({}), view => { latest = view; });
  await controller.start();
  await controller.send('Browse');
  await controller.retry();
  assert.equal(sends, 1);
  assert.equal(latest.session.revision, 2);
  assert.equal(latest.retryable, false);
});

test('photo click rereads saved item before opening and updates focus', async () => {
  let sent;
  const client = {
    startAssistantConversation: async payload => {
      assert.equal(payload.request_id, 'read-pilot-v1');
      return { conversation_id: 'id', revision: 5 };
    },
    readAssistantConversation: async (id, payload) => {
      sent = payload;
      return { conversation_id: id, revision: 6, focus: 'target', result_sets: [{ items: [{ listing_id: 'target', images: ['fresh'] }] }] };
    },
  };
  const controller = createConversationController(client, async () => ({}), () => {});
  await controller.start();
  const session = await controller.viewPhotos({ listing_id: 'target', title: 'Coat' });
  assert.equal(sent.action, 'photos');
  assert.equal(sent.expected_revision, 5);
  assert.equal(session.focus, 'target');
  assert.deepEqual(session.result_sets[0].items[0].images, ['fresh']);
});
test('listing transcript weaves upload follow-ups into chat without duplicate shared turns', async () => {
  const { listingConversationMessages } = await import('./assistantConversation.js');
  const message = (role, content) => ({ role, content });
  const shared = [message('user', 'New'), message('assistant', 'What size?')];
  const parent = [message('user', 'Create a listing'), message('assistant', 'Add photos'), ...shared];
  const child = [message('user', 'I uploaded these original photos. Please check the evidence and guide me through creating a private listing draft.'), message('assistant', 'What condition?'), ...shared];
  assert.deepEqual(listingConversationMessages(parent, child).map(m => m.content),
    ['Create a listing', 'Add photos', 'Added photos.', 'What condition?', 'New', 'What size?']);
  assert.deepEqual(listingConversationMessages(parent).map(m => m.content), parent.map(m => m.content));
});

test('listing transcript uses earliest shared timestamps and preserves distinct repeated messages', async () => {
  const { listingConversationMessages } = await import('./assistantConversation.js');
  const message = (role, content, time) => ({ role, content, created_at: time });
  const parent = [message('user', 'New', '03'), message('assistant', 'Saved', '04')];
  const child = [message('user', 'New', '01'), message('assistant', 'Saved', '02'), message('user', 'New', '05')];
  assert.deepEqual(listingConversationMessages(parent, child).map(m => m.created_at), ['01', '02', '05']);
});
test('intake photo panel follows the latest upload before the next question; review stays current', async () => {
  const { listingPanelPosition } = await import('./assistantConversation.js');
  const messages = [{ role: 'user', content: 'Create listing' }, { role: 'user', content: 'Added photos.' },
    { role: 'assistant', content: 'What condition?' }];
  assert.equal(listingPanelPosition(messages, 'collecting'), 2);
  assert.equal(listingPanelPosition(messages, 'review_ready'), 2);
  assert.equal(listingPanelPosition([], 'collecting'), 0);
  assert.equal(listingPanelPosition([...messages, { role: 'user', content: 'Added photos.' },
    { role: 'assistant', content: 'What size?' }], 'collecting'), 4);
});
test('chronological timeline retains coverage before facts and review before later corrections', async () => {
  const { chronologicalChat } = await import('./assistantConversation.js');
  const at = n => `2026-10-21T10:00:0${n}Z`;
  const parent = [{ role: 'assistant', content: 'Legacy introduction' },
    { role: 'user', content: 'New', created_at: at(3) },
    { role: 'assistant', content: 'What size?', created_at: at(4) },
    { role: 'user', content: 'Change size', created_at: at(7) }];
  const child = { stage: 'published', messages: [], timeline_events: [
    { id: 'p', kind: 'photos', created_at: at(1), snapshot: { photos: [{ image_id: 'one', url: '/one' }] } },
    { id: 'c', kind: 'coverage', created_at: at(2), snapshot: { photos: [{}], evidence: { status: 'checked', missing_required: [] } } },
    { id: 'r', kind: 'actions', created_at: at(6), snapshot: { stage: 'review_ready', facts: { size: '10' } } },
  ] };
  const rows = chronologicalChat(parent, child);
  assert.deepEqual(rows.map(row => row.id || row.content), ['Legacy introduction', 'p', 'c', 'New', 'What size?', 'r', 'Change size']);
  assert.equal(rows.filter(row => row.timeline_kind === 'actions' && row.isCurrent).length, 1);
  assert.match(rows.find(row => row.id === 'c').content, /All required photo views/);
});

test('timeline retains previous assessments and result cards with their producing replies', async () => {
  const { chronologicalChat } = await import('./assistantConversation.js');
  const parent = [{ role: 'assistant', content: 'Found first', created_at: '2026-10-21T10:00:01Z', result_sets: [{ id: 'first', items: [] }] },
    { role: 'assistant', content: 'Found second', created_at: '2026-10-21T10:00:05Z', result_sets: [{ id: 'second', items: [] }] }];
  const child = { timeline_events: [
    { id: 'old', kind: 'coverage', created_at: '2026-10-21T10:00:02Z', snapshot: { photos: [{}], evidence: { status: 'checked', missing_required: [] } } },
    { id: 'reset', kind: 'coverage', created_at: '2026-10-21T10:00:03Z', snapshot: { photos: [{}], evidence: null } },
  ] };
  const rows = chronologicalChat(parent, child);
  assert.equal(rows[0].result_sets[0].id, 'first');
  assert.equal(rows.at(-1).result_sets[0].id, 'second');
  assert.match(rows[2].content, /not been assessed/);
  assert.equal(rows[1].isCurrent, false);
});
test('timeline estimated values use dollar formatting with separators and cents', async () => {
  const { chronologicalChat } = await import('./assistantConversation.js');
  for (const [value, expected] of [[24, '$24'], [3100, '$3,100'], [23.5, '$23.50'], [0, '$0']]) {
    const [row] = chronologicalChat([], { timeline_events: [{ id: 'value', kind: 'actions',
      created_at: '2026-10-21T10:00:00Z', snapshot: { stage: 'published', listing: { title: 'Shorts', estimated_value: value } } }] });
    assert.ok(row.content.includes(`Estimated value: ${expected}`));
  }
});
